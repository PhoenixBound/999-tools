# Script to convert back and forth between etc/staff.dat and JSON file
# for 999: Nine Hours, Nine Persons, Nine Doors (DS)
# by PhoenixBound
# Last updated: 2025-03-21

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

def read_credits_list(data, offset, encoding):
    i = offset
    lines = []
    while True:
        text = read_str(data, int.from_bytes(data[i:i+4], 'little'))
        lines.append(text)
        i += 4
        if text == '[E]':
            break
    return lines

def make_sir0_from_dict(thing, display_encoding):
    string_data = bytearray()
    credits_ptrs = []
    credits_pointer_locs = []
    main_ptrs = []
    main_pointer_locs = []
    
    sir_header_size = 0x10
    
    for (k, v) in thing.items():
        # Add id string (we'll fix the pointer later)
        main_pointer_locs.append((len(main_ptrs) * 4, '.str'))
        main_ptrs.append(len(string_data))
        string_data.extend(to_encoded_str(k))
        
        # Add pointer to list
        main_pointer_locs.append((len(main_ptrs) * 4, '.credits'))
        main_ptrs.append(len(credits_ptrs) * 4)
        for s in v:
            # Add strings for all the credits entries
            credits_pointer_locs.append((len(credits_ptrs) * 4, '.str'))
            credits_ptrs.append(len(string_data))
            string_data.extend(to_encoded_display_str(s, display_encoding))
        # Add extra null pointer at the end of each credits list
        # TODO: do we need to add pointer metadata for this...?
        credits_ptrs.append(0)
    
    # Align string_data to a multiple of 4 bytes if necessary
    string_data.extend(b'\xAA' * ((4 - len(string_data) % 4) % 4))
    
    # Add the rest of the main data
    # First the null id string
    main_ptrs.append(0)
    # Then the pointer past the end of the credits string table
    main_pointer_locs.append((len(main_ptrs) * 4, '.credits'))
    main_ptrs.append(len(credits_ptrs) * 4)
    
    
    for (p, t) in credits_pointer_locs:
        assert t == '.str'
        credits_ptrs[p // 4] += sir_header_size

    for (p, t) in main_pointer_locs:
        if t == '.str':
            main_ptrs[p // 4] += sir_header_size
        elif t == '.credits':
            main_ptrs[p // 4] += sir_header_size + len(string_data)

    pointer_locs = [4, 8]
    pointer_locs.extend([x[0] + sir_header_size + len(string_data) for x in credits_pointer_locs])
    pointer_locs.extend([x[0] + sir_header_size + len(string_data) + len(credits_ptrs)*4 for x in main_pointer_locs])
    
    # Go through every entry (except the first one) in pointer_locs starting from the end
    i = len(pointer_locs) - 1 
    while i > 0:
        # Turn it into the distance from the previous pointer location
        pointer_locs[i] -= pointer_locs[i - 1]
        i -= 1
    
    out_file_data = bytearray()
    out_file_data.extend(b'SIR0')
    out_file_data.extend((sir_header_size + len(string_data) + len(credits_ptrs)*4).to_bytes(4, 'little'))
    out_file_data.extend(((sir_header_size + len(string_data) + len(credits_ptrs)*4 + len(main_ptrs)*4 + 0xF) & ~0xF).to_bytes(4, 'little'))
    out_file_data.extend(b'\x00\x00\x00\x00')
    out_file_data.extend(string_data)
    for x in credits_ptrs:
        out_file_data.extend(x.to_bytes(4, 'little'))
    for x in main_ptrs:
        out_file_data.extend(x.to_bytes(4, 'little'))
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

def dump(staff_dat, display_encoding=None):
    if staff_dat[0:3] != b'SIR':
        raise RuntimeError('File is not a SIR0 or SIR1 file')
    if staff_dat[3:4] != b'0':
        raise RuntimeError('Unsupported SIR{X} version -- only SIR0 (32-bit pointers) is supported for now')

    main_data = int.from_bytes(staff_dat[4:8], 'little')
    # We ignore the pointer metadata because we're cool like that

    # Read all the pairs of credits IDs and credits pointers
    endings = []
    header_ptr = main_data
    while True:
        id_ptr = int.from_bytes(staff_dat[header_ptr:header_ptr+4], 'little')
        credits_ptr = int.from_bytes(staff_dat[header_ptr+4:header_ptr+8], 'little')
        if id_ptr == 0:
            assert credits_ptr == main_data
            break

        assert 0x10 <= id_ptr < main_data
        assert 0x10 <= credits_ptr < main_data
        
        endings.append((id_ptr, credits_ptr))
        header_ptr += 8

    # Then turn it into the structure that will make a good JSON, and make a dict out of that
    return {                                                                       \
        read_str(staff_dat, id): read_credits_list(staff_dat, c, display_encoding) \
        for (id, c) in endings                                                     \
    }


def main(args):
    if len(args) != 4 and len(args) != 5:
        print('Usage:')
        print(args[0], 'dump <staff.dat> <output.json> [--latin1]')
        print(args[0], 'make <edited.json> <new-staff.dat> [--latin1]')
        exit(1)

    display_encoding = 'mskanji'
    if len(args) == 5:
        if args[4] == '--latin1':
            display_encoding = 'latin_1'
        else:
            raise RuntimeError(f'Unrecognized 5th argument "{args[4]}"')

    if args[1] == 'dump':
        staff_dat = None
        with open(args[2], 'rb') as f:
            staff_dat = f.read()

        endings_structured = dump(staff_dat, display_encoding)

        with open(args[3], 'w', encoding='utf-8', newline='\n') as f:
            json.dump(endings_structured, f, ensure_ascii=False, indent=4)
    elif args[1] == 'make':
        with open(args[2], 'r', encoding='utf-8') as f:
            endings_structured = json.load(f)
        
        # Double check that it matches the schema
        assert type(endings_structured) == dict
        for k in endings_structured.keys():
            assert type(k) == str
        for v in endings_structured.values():
            assert type(v) == list
            for (i, s) in enumerate(v):
                assert type(s) == str
                if i == len(v) - 1:
                    assert s == '[E]'
        
        output = make_sir0_from_dict(endings_structured, display_encoding)
        with open(args[3], 'wb') as f:
            f.write(output)
    else:
        print(f'Invalid command "{args[1]}" -- expected "dump" or "make"')
        exit(1)

if __name__ == '__main__':
    main(sys.argv)