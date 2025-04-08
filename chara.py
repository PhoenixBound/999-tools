# Script to convert back and forth between etc/chara.dat and JSON file
# for 999: Nine Hours, Nine Persons, Nine Doors (DS)
# by PhoenixBound
# Last updated: 2025-04-07

from io import StringIO
import itertools
import json
import sys

def read_str(data, offset):
    end_index = data.find(0, offset)
    return data[offset:end_index].decode('mskanji')

def read_display_str(data, offset, encoding):
    end_index = data.find(0, offset)
    if encoding is None:
        encoding = 'mskanji'
    return data[offset:end_index].decode(encoding)

def to_encoded_str(s):
    return s.encode('mskanji') + b'\0'

def to_encoded_display_str(s, encoding):
    if encoding is None:
        encoding = 'mskanji'
    return s.encode(encoding) + b'\0'

def dump(chara_dat):
    # Hardcode this. "Nice" PT-BR dumping is hard because the English dat still
    # includes SJIS characters for ??? and "None" names
    display_encoding = 'mskanji'
    
    if chara_dat[0:3] != b'SIR':
        raise RuntimeError('File is not a SIR0 or SIR1 file')
    if chara_dat[3:4] != b'0':
        raise RuntimeError('Unsupported SIR{X} version -- only SIR0 (32-bit pointers) is supported for now')

    main_data = int.from_bytes(chara_dat[4:8], 'little')
    # We ignore the pointer metadata because we're cool like that

    structured = []
    while True:
        id_ptr = int.from_bytes(chara_dat[main_data:main_data+4], 'little')
        if id_ptr == 0:
            break
        display_name_ptr = int.from_bytes(chara_dat[main_data+4:main_data+8], 'little')
        unk8 = int.from_bytes(chara_dat[main_data+8:main_data+12], 'little')
        unkC = int.from_bytes(chara_dat[main_data+12:main_data+16], 'little')
        sfx = int.from_bytes(chara_dat[main_data+16:main_data+20], 'little')
        
        structured.append({ \
            'id': read_str(chara_dat, id_ptr), \
            'display_name': read_display_str(chara_dat, display_name_ptr, display_encoding), \
            'character': read_str(chara_dat, unk8), \
            'unkC': unkC, \
            'sfx': read_str(chara_dat, sfx) \
        })
        
        main_data += 0x14

    return structured

def make_sir0_from_list(structured):
    # Hardcode this. "Nice" PT-BR dumping is hard because the English dat still
    # includes SJIS characters for ??? and "None" names
    display_encoding = 'mskanji'
    
    string_data = bytearray()
    main_data = bytearray()
    main_pointer_locs = []

    sir_header_size = 0x10

    for chara in structured:
        main_pointer_locs.append((len(main_data), '.str'))
        main_data.extend(len(string_data).to_bytes(4, 'little'))
        string_data.extend(to_encoded_str(chara['id']))
        
        main_pointer_locs.append((len(main_data), '.str'))
        main_data.extend(len(string_data).to_bytes(4, 'little'))
        string_data.extend(to_encoded_display_str(chara['display_name'], display_encoding))
        
        main_pointer_locs.append((len(main_data), '.str'))
        main_data.extend(len(string_data).to_bytes(4, 'little'))
        string_data.extend(to_encoded_str(chara['character']))
        
        main_data.extend(chara['unkC'].to_bytes(4, 'little'))
        
        main_pointer_locs.append((len(main_data), '.str'))
        main_data.extend(len(string_data).to_bytes(4, 'little'))
        string_data.extend(to_encoded_str(chara['sfx']))
    # Align string_data to a multiple of 4 bytes if necessary
    while len(string_data) % 4 != 0:
        string_data.append(0xAA)

    # Add the rest of the main data
    # First a null pointer
    main_data.extend(b'\x00\x00\x00\x00')
    # Then a pointer to the beginning of the main data
    main_pointer_locs.append((len(main_data), '.main'))
    main_data.extend(b'\x00\x00\x00\x00')
    # Then, four more zeroes for some reason...
    main_data.extend(b'\x00\x00\x00\x00')

    # Fix the literal addresses of all pointers so that they match their pointees' file addresses
    for (p, t) in main_pointer_locs:
        old_pointer = int.from_bytes(main_data[p:p+4], 'little')

        # Fix the offset based on what section the pointee is in
        if t == '.str':
            new_pointer = old_pointer + sir_header_size
        else:
            assert t == '.main'
            new_pointer = old_pointer + sir_header_size + len(string_data)

        main_data[p:p+4] = new_pointer.to_bytes(4, 'little')

    # Compile a list of all the pointers' locations in the file
    pointer_locs = [4, 8]
    pointer_locs.extend([x[0] + sir_header_size + len(string_data) for x in main_pointer_locs])

    # Go through every entry (except the first one) in pointer_locs starting from the end
    i = len(pointer_locs) - 1 
    while i > 0:
        # Turn it into the distance from the previous pointer location
        pointer_locs[i] -= pointer_locs[i - 1]
        i -= 1
    del i

    out_file_data = bytearray()
    out_file_data.extend(b'SIR0')
    out_file_data.extend((sir_header_size + len(string_data)).to_bytes(4, 'little'))
    out_file_data.extend(((sir_header_size + len(string_data) + len(main_data) + 0xF) & ~0xF).to_bytes(4, 'little'))
    out_file_data.extend(b'\x00\x00\x00\x00')
    out_file_data.extend(string_data)
    out_file_data.extend(main_data)
    while len(out_file_data) % 16 != 0:
        out_file_data.append(0xAA)

    # Now, finally, add the pointer metadata
    d = bytearray()
    for loc in pointer_locs:
        d.clear()
        while loc != (loc & 0x7F):
            d.append(loc & 0x7F)
            loc >>= 7
        d.append(loc)
        d.reverse()
        for i in range(len(d) - 1):
            d[i] |= 0x80
        out_file_data.extend(d)
    del d
    out_file_data.append(0)

    while len(out_file_data) % 16 != 0:
        out_file_data.append(0xAA)

    return out_file_data

def print_usage(args):
    print('Usage:')
    print(f'    python {args[0]} dump <chara.dat> <output.json>')
    print(f'    python {args[0]} make <edited.json> <new-chara.dat>')

def main(args):
    if len(args) >= 2 and args[1] == 'dump':
        if len(args) != 4:
            print_usage(args)
            return 1

        chara_dat = None
        with open(args[2], 'rb') as f:
            chara_dat = f.read()

        structured = dump(chara_dat)

        with open(args[3], 'w', encoding='utf-8', newline='\n') as f:
            json.dump(structured, f, ensure_ascii=False, indent=4)
    elif len(args) >= 2 and args[1] == 'make':
        if len(args) != 4:
            print_usage(args)
            return 1

        structured = None
        with open(args[2], 'r', encoding='utf-8') as f:
            structured = json.load(f)

        chara_dat = make_sir0_from_list(structured)

        with open(args[3], 'wb') as f:
            f.write(chara_dat)
    else:
        if len(args) == 1:
            print_usage(args)
            return 1
        print(f'Invalid command "{args[1]}" -- expected "dump" or "make"')
        return 1

if __name__ == '__main__':
    exit(main(sys.argv))
