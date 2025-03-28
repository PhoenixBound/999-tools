# BG.dat image extraction/insertion script
# for 999: Nine Hours, Nine Persons, Nine Doors (DS)
# by PhoenixBound
# Last updated: 2025-03-21

from io import StringIO
import itertools
import json
import sys

from PIL import Image

# https://stackoverflow.com/a/8991553
# https://docs.python.org/3/library/itertools.html#itertools.batched
# I use Python 3.10, so I can't use `itertools.batched`
def batched(iterable, n, *, strict=False):
    # batched('ABCDEFG', 3) → ABC DEF G
    if n < 1:
        raise ValueError('n must be at least one')
    iterator = iter(iterable)
    while batch := tuple(itertools.islice(iterator, n)):
        if strict and len(batch) != n:
            raise ValueError('batched(): incomplete batch')
        yield batch

def as_signed_byte(b):
    return (b + 128) % 256 - 128

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

def read_char(kanji_dat, offset):
    code = bytearray(kanji_dat[offset:offset+2])
    if code[1] != 0:
        code.reverse()
    else:
        # print('Before:', code)
        code.pop()
        # print('After:', code)
    code = code.decode('mskanji')

    unk2 = as_signed_byte(kanji_dat[offset + 2])
    unk3 = as_signed_byte(kanji_dat[offset + 3])
    unk4 = as_signed_byte(kanji_dat[offset + 4])
    unk5 = kanji_dat[offset + 5]
    width = kanji_dat[offset + 6]
    unk7 = kanji_dat[offset + 7]
    gfx = kanji_dat[offset+8:offset+8+unk5*2]

    return {\
        'code': code,          \
        'left_offset': unk2,   \
        'top_offset': unk3,    \
        'unk4': unk4,          \
        'canvas_height': unk5, \
        'width': width,        \
        'unk7': unk7,          \
        'gfx': gfx             \
    }

def cheaply_visualize_char(raw_gfx):
    rows = []
    for i in range(0, len(raw_gfx), 2):
        with StringIO() as row_text:
            row_bytes = int.from_bytes(raw_gfx[i:i+2], 'little')

            for j in range(14):
                row_text.write('#' if (row_bytes & 1) != 0 else '.')
                row_bytes >>= 1

            rows.append(row_text.getvalue())
    return '\n'.join(rows)

def dump(kanji_dat):
    if kanji_dat[0:3] != b'SIR':
        raise RuntimeError('File is not a SIR0 or SIR1 file')
    if kanji_dat[3:4] != b'0':
        raise RuntimeError('Unsupported SIR{X} version -- only SIR0 (32-bit pointers) is supported for now')

    main_data = int.from_bytes(kanji_dat[4:8], 'little')
    # We ignore the pointer metadata because we're cool like that

    char_count = int.from_bytes(kanji_dat[main_data:main_data+4], 'little')
    num4 = int.from_bytes(kanji_dat[main_data+4:main_data+8], 'little')
    num8 = int.from_bytes(kanji_dat[main_data+8:main_data+12], 'little')
    char_data_base = int.from_bytes(kanji_dat[main_data+12:main_data+16], 'little')

    char_offsets = kanji_dat[main_data+16:main_data+16+char_count*2]
    char_offsets = [int.from_bytes(char_offsets[i:i+2], 'little') for i in range(0, char_count*2, 2)]
    chars = [read_char(kanji_dat, char_data_base + offset*2) for offset in char_offsets]
    del char_offsets

    structured = {     \
        'unk4': num4,  \
        'unk8': num8,  \
        'chars': chars \
    }

    return structured

def build_image(data, width):
    height = (len(data['chars']) + width - 1) // width
    img = Image.new('1', (width*14, height*14))

    img_row = 0
    img_col = 0
    for char in data['chars']:
        canvas_height = char['canvas_height']
        one_char = Image.new('1', (14, canvas_height))
        for (row, row_data) in zip(range(canvas_height), batched(char['gfx'], 2, strict=True)):
            row_data_combined = row_data[0] | (row_data[1] << 8)
            for col in range(14):
                one_char.putpixel((col, row), row_data_combined & 1)
                row_data_combined >>= 1
        img.paste(one_char, (img_col * 14, \
                             img_row * 14, \
                             img_col * 14 + 14, \
                             img_row * 14 + canvas_height))
        img_col += 1
        if img_col == width:
            img_col = 0
            img_row += 1

    return img

def read_chars_from_image(img):
    width = img.width
    height = img.height
    if width % 14 != 0 or height % 14 != 0:
        raise ValueError(f'Bad image dimensions {width}x{height} -- dimensions must be multiples of 14')
    # Silently convert to a pure black and white image, based on a threshold of (rec_601_luma < 128)
    img = img.convert('1', dither=None)
    chars = []

    for row in range(0, height, 14):
        for col in range(0, width, 14):
            char_image = img.crop((col, row, col + 14, row + 14))
            char = bytearray()
            for char_row in range(14):
                row_data = 0
                for char_col in range(14):
                    row_data >>= 1
                    pixel = char_image.getpixel((char_col, char_row))
                    assert pixel == 0 or pixel == 255
                    pixel >>= 7
                    row_data |= pixel << 13
                char.extend(row_data.to_bytes(2, 'little'))
            chars.append(char)

    return chars

def make_sir0_from_dict(structured):
    character_data = bytearray()
    main_data = bytearray()
    main_pointer_locs = []

    sir_header_size = 0x10

    # TODO: rewrite for kanji.dat
    main_data.extend(len(structured['chars']).to_bytes(4, 'little'))
    main_data.extend(structured['unk4'].to_bytes(4, 'little'))
    main_data.extend(structured['unk8'].to_bytes(4, 'little'))
    main_pointer_locs.append((len(main_data), '.chr'))
    main_data.extend((0).to_bytes(4, 'little'))

    for char in structured['chars']:
        main_data.extend((len(character_data) // 2).to_bytes(2, 'little'))

        # TODO: read a different field that can contain arbitrary bytes, to
        # allow for Frankenstein encodings like the pt-br fan translation
        code = bytearray(char['code'].encode('mskanji'))
        if len(code) == 1:
            code.append(0)
        else:
            code.reverse()
        character_data.extend(code)
        del code

        character_data.append(char['left_offset'] & 0xFF)
        character_data.append(char['top_offset'] & 0xFF)
        character_data.append(char['unk4'] & 0xFF)
        character_data.append(char['canvas_height'])
        character_data.append(char['width'])
        character_data.append(char['unk7'])
        character_data.extend(char['gfx'])
    # Align character_data to a multiple of 4 bytes if necessary
    while len(character_data) % 4 != 0:
        character_data.append(0xAA)

    # Fix the literal addresses of all pointers so that they match their pointees' file addresses
    for (p, t) in main_pointer_locs:
        old_pointer = int.from_bytes(main_data[p:p+4], 'little')

        assert t == '.chr'
        new_pointer = old_pointer + sir_header_size

        main_data[p:p+4] = new_pointer.to_bytes(4, 'little')

    # Compile a list of all the pointers' locations in the file
    pointer_locs = [4, 8]
    pointer_locs.extend([x[0] + sir_header_size + len(character_data) for x in main_pointer_locs])

    # Go through every entry (except the first one) in pointer_locs starting from the end
    i = len(pointer_locs) - 1 
    while i > 0:
        # Turn it into the distance from the previous pointer location
        pointer_locs[i] -= pointer_locs[i - 1]
        i -= 1
    del i

    out_file_data = bytearray()
    out_file_data.extend(b'SIR0')
    out_file_data.extend((sir_header_size + len(character_data)).to_bytes(4, 'little'))
    out_file_data.extend(((sir_header_size + len(character_data) + len(main_data) + 0xF) & ~0xF).to_bytes(4, 'little'))
    out_file_data.extend(b'\x00\x00\x00\x00')
    out_file_data.extend(character_data)
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
    print(f'    python {args[0]} dump <kanji.dat> <output.png> <output.json>')
    print(f'    python {args[0]} make <edited.png> <edited.json> <new-kanji.dat>')

def main(args):
    if args[1] == 'dump':
        if len(args) != 5:
            print_usage(args)
            return 1

        kanji_dat = None
        with open(args[2], 'rb') as f:
            kanji_dat = f.read()

        structured = dump(kanji_dat)

        img = build_image(structured, 32)
        img.save(args[3], format='PNG')

        # Remove the actual image data before outputting to JSON
        for (i, char) in enumerate(structured['chars']):
            del char['gfx']
            char['gfx_pos'] = i

        with open(args[4], 'w', encoding='utf-8', newline='\n') as f:
            json.dump(structured, f, ensure_ascii=False, indent=4)
    elif args[1] == 'make':
        if len(args) != 5:
            print_usage(args)
            return 1

        gfx_list = None
        with Image.open(args[2], formats=('PNG',)) as img:
            gfx_list = read_chars_from_image(img)
        structured = None
        with open(args[3], 'r', encoding='utf-8') as f:
            structured = json.load(f)

        # Add the image data to every character
        for char in structured['chars']:
            gfx_pos = char.pop('gfx_pos')
            canvas_height = char['canvas_height']
            char['gfx'] = gfx_list[gfx_pos][0:canvas_height*2]

        del gfx_list

        # Sort characters by SJIS byte sequence (the game does a binary search)
        def sjis_key(c):
            code = c['code'].encode('mskanji')
            if len(code) == 1:
                return b'\x00' + code
            else:
                return code

        structured['chars'].sort(key=sjis_key)

        kanji_dat = make_sir0_from_dict(structured)

        with open(args[4], 'wb') as f:
            f.write(kanji_dat)
    else:
        print(f'Invalid command "{args[1]}" -- expected "dump" or "make"')
        return 1

if __name__ == '__main__':
    exit(main(sys.argv))
