# Script to convert back and forth between etc/room.dat and JSON file
# for 999: Nine Hours, Nine Persons, Nine Doors (DS)
# by PhoenixBound
# Last updated: 2025-02-01

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

def read_rooms_list(data, offset, display_encoding):
    rooms = []
    it = offset
    while True:
        str1_offset = int.from_bytes(data[it:it+4], 'little')
        if str1_offset == 0:
            break
        str2_offset = int.from_bytes(data[it+4:it+8], 'little')
        str3_offset = int.from_bytes(data[it+8:it+12], 'little')
        str4_offset = int.from_bytes(data[it+12:it+16], 'little')
        str5_offset = int.from_bytes(data[it+16:it+20], 'little')
        
        rooms.append({
            'id': read_str(data, str1_offset),
            'name': read_display_str(data, str2_offset, display_encoding),
            'unlock_var': read_str(data, str3_offset),
            # I assume these two are just BG filenames...? But the first one might be a room name
            'unk10': read_str(data, str4_offset),
            'unk14': read_str(data, str5_offset),
        })
        it += 0x14
    return rooms

def make_sir0_from_obj_list(thing, display_encoding):
    string_data = bytearray()
    rooms_data = []
    rooms_pointer_locs = []
    main_ptrs = []
    main_pointer_locs = []
    
    sir_header_size = 0x10
    
    for obj in thing:
        obj_id = obj['id']
        obj_stages = obj['stages']
        
        # Add id string
        main_pointer_locs.append((len(main_ptrs) * 4, '.str'))
        main_ptrs.append(len(string_data))
        string_data.extend(to_encoded_str(obj_id))
        
        # Add pointer to rooms list
        main_pointer_locs.append((len(main_ptrs) * 4, '.rooms'))
        main_ptrs.append(len(rooms_data) * 4)
        for r in obj_stages:
            stage_id = r['id']
            name = r['name']
            unlock_var = r['unlock_var']
            unk10 = r['unk10']
            unk14 = r['unk14']
            
            rooms_pointer_locs.append((len(rooms_data) * 4, '.str'))
            rooms_data.append(len(string_data))
            string_data.extend(to_encoded_str(stage_id))
            
            rooms_pointer_locs.append((len(rooms_data) * 4, '.str'))
            rooms_data.append(len(string_data))
            string_data.extend(to_encoded_display_str(name, display_encoding))
            
            rooms_pointer_locs.append((len(rooms_data) * 4, '.str'))
            rooms_data.append(len(string_data))
            string_data.extend(to_encoded_str(unlock_var))
            
            rooms_pointer_locs.append((len(rooms_data) * 4, '.str'))
            rooms_data.append(len(string_data))
            string_data.extend(to_encoded_str(unk10))
            
            rooms_pointer_locs.append((len(rooms_data) * 4, '.str'))
            rooms_data.append(len(string_data))
            string_data.extend(to_encoded_str(unk14))

        # Add extra null pointer at the end of each rooms list, to mark the end
        # Null pointers don't get pointer metadata, since that would make them
        # no longer look like null/0 after the file is loaded
        rooms_data.append(0)
    
    # Align string_data to a multiple of 4 bytes if necessary
    string_data.extend(b'\xAA' * ((4 - len(string_data) % 4) % 4))
    
    # Add the rest of the main data
    # First the null id string
    main_ptrs.append(0)
    # Then the pointer past the end of the credits string table
    main_pointer_locs.append((len(main_ptrs) * 4, '.rooms'))
    main_ptrs.append(len(rooms_data) * 4)
    
    
    for (p, t) in rooms_pointer_locs:
        assert t == '.str'
        rooms_data[p // 4] += sir_header_size

    for (p, t) in main_pointer_locs:
        if t == '.str':
            main_ptrs[p // 4] += sir_header_size
        elif t == '.rooms':
            main_ptrs[p // 4] += sir_header_size + len(string_data)

    pointer_locs = [4, 8]
    pointer_locs.extend([x[0] + sir_header_size + len(string_data) for x in rooms_pointer_locs])
    pointer_locs.extend([x[0] + sir_header_size + len(string_data) + len(rooms_data)*4 for x in main_pointer_locs])
    
    # Go through every entry (except the first one) in pointer_locs starting from the end
    i = len(pointer_locs) - 1 
    while i > 0:
        # Turn it into the distance from the previous pointer location
        pointer_locs[i] -= pointer_locs[i - 1]
        i -= 1
    del i
    
    out_file_data = bytearray()
    out_file_data.extend(b'SIR0')
    out_file_data.extend((sir_header_size + len(string_data) + len(rooms_data)*4).to_bytes(4, 'little'))
    out_file_data.extend(((sir_header_size + len(string_data) + len(rooms_data)*4 + len(main_ptrs)*4 + 0xF) & ~0xF).to_bytes(4, 'little'))
    out_file_data.extend(b'\x00\x00\x00\x00')
    out_file_data.extend(string_data)
    for x in rooms_data:
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

def dump(room_dat, display_encoding):
    if room_dat[0:3] != b'SIR':
        raise RuntimeError('File is not a SIR0 or SIR1 file')
    if room_dat[3:4] != b'0':
        raise RuntimeError('Unsupported SIR{X} version -- only SIR0 (32-bit pointers) is supported for now')

    main_data = int.from_bytes(room_dat[4:8], 'little')
    # We ignore the pointer metadata because we're cool like that

    # Read all the pairs of category names and sets of escape room stages
    escape_rooms = []
    header_ptr = main_data
    while True:
        id_ptr = int.from_bytes(room_dat[header_ptr:header_ptr+4], 'little')
        rooms_ptr = int.from_bytes(room_dat[header_ptr+4:header_ptr+8], 'little')
        if id_ptr == 0:
            assert rooms_ptr == main_data
            break

        assert 0x10 <= id_ptr < main_data
        assert 0x10 <= rooms_ptr < main_data
        
        escape_rooms.append((id_ptr, rooms_ptr))
        header_ptr += 8

    # Then turn it into the structure that will make a good JSON, and make a dict out of that
    structured = [{
        'id': read_str(room_dat, id),
        'stages': read_rooms_list(room_dat, rooms, display_encoding)
    } for (id, rooms) in escape_rooms]

    return structured

def main(args):
    if len(args) != 4 and len(args) != 5:
        print('Usage:')
        print(args[0], 'dump <room.dat> <output.json> [--ptbr]')
        print(args[0], 'make <edited.json> <new-room.dat> [--ptbr]')
        return 1
    
    display_encoding = None
    # if len(args) == 5 and args[4].startswith('--display-encoding='):
    #     # Everything after the = sign
    #     display_encoding = args[4][args[4].index('='):]
    if len(args) == 5 and args[4] == '--ptbr':
        display_encoding = 'latin_1'
    
    if args[1] == 'dump':
        room_dat = None
        with open(args[2], 'rb') as f:
            room_dat = f.read()

        structured = dump(room_dat, display_encoding)

        with open(args[3], 'w', encoding='utf-8', newline='\n') as f:
            json.dump(structured, f, ensure_ascii=False, indent=4)
    elif args[1] == 'make':
        with open(args[2], 'r', encoding='utf-8') as f:
            structured = json.load(f)
        
        # Double check that it matches the schema
        # ...or not, because that's kind of annoying
        
        output = make_sir0_from_obj_list(structured, display_encoding)
        
        with open(args[3], 'wb') as f:
            f.write(output)
    else:
        print(f'Invalid command "{args[1]}" -- expected "dump" or "make"')
        return 1

if __name__ == '__main__':
    exit(main(sys.argv))