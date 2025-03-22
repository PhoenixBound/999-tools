# BG.dat image extraction/insertion script
# for 999: Nine Hours, Nine Persons, Nine Doors (DS)
# by PhoenixBound
# Last updated: 2025-03-21

# import json
import sys

from PIL import Image

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

def at6p_decompress(data):
    assert data[0:4] == b'AT6P'
    unk = data[4]
    compressed_size = int.from_bytes(data[5:7], 'little')
    assert compressed_size == len(data)
    # assert int.from_bytes(data[7:16], 'little') == 0
    decompressed_size = int.from_bytes(data[16:19], 'little')
    assert data[19] == 0
    
    previous = data[20]
    current = previous
    
    output = bytearray()
    output.append(current)
    
    # assert data[21] == 0
    
    i_byte = 0x16
    i_bit = 0
    
    while len(output) < decompressed_size:
        bit_count = 0
        while (data[i_byte] >> i_bit) & 1 == 0:
            bit_count += 1
            i_bit += 1
            if i_bit == 8:
                i_bit = 0
                i_byte += 1
            
            if bit_count > 8:
                raise RuntimeError('Exponential-Golomb decoding failure')
                
        # Advance past the 1 bit
        i_bit += 1
        if i_bit == 8:
            i_bit = 0
            i_byte += 1
        # Read the actual data
        d = 0
        for j in range(bit_count):
            bit = (data[i_byte] >> i_bit) & 1
            i_bit += 1
            if i_bit == 8:
                i_bit = 0
                i_byte += 1
            d |= bit << j
        # Add bias to complete exponential-golomb decoding
        d += (1 << bit_count) - 1
            
        # Chunsoft loves encoding sign-magnitude values as variable-width positive integers
        # IMPORTANT: `previous` is not updated when repeating the current byte (sign == 1 and magnitude == 0)
        sign = (d & 1) * -2 + 1
        magnitude = d >> 1
        if sign == -1 and magnitude == 0:
            # -0 means "output the previous byte"
            previous, current = current, previous
        elif magnitude != 0:
            previous = current
            current += magnitude * sign
            current &= 0xFF
        output.append(current)
    
    return output

def at6p_compress(data):
    output = bytearray()
    output.extend(b'AT6P')
    # I dunno how to calculate this. I originally put an F (for "frustrating" of course...)
    # but I want to see if it's maybe a checksum or what
    output.extend(b'\x00')
    # Placeholder: compressed size
    output.extend(b'\x00\x00')
    output.extend(b'\x00' * 9)
    output.extend(len(data).to_bytes(3, 'little'))
    output.append(0)
    output.append(data[0])
    output.append(0)
    
    compressed_byte = 0
    compressed_bit_pos = 0
    
    previous = data[0]
    
    for (i, b) in zip(range(1, len(data)), data[1:]):
        delta = b - data[i - 1]
        # Make signed
        delta = ((delta + 0x80) & 0xFF) - 0x80
        sign_bit = int(delta < 0)
        magnitude = abs(delta)
        
        word = None
        if magnitude == 0:
            word = 0
        elif b == previous:
            word = 1
            previous = data[i - 1]
        else:
            word = magnitude * 2 + sign_bit
            previous = data[i - 1]

        # Encode the word as bits, using the method mentioned on the "exponential-golomb"
        # Wikipedia page
        word += 1
        
        # Add initial 0 bits
        for j in range(word.bit_length() - 1):
            # compressed_byte |= 0
            compressed_bit_pos += 1
            if compressed_bit_pos == 8:
                compressed_bit_pos = 0
                output.append(compressed_byte)
                compressed_byte = 0
        # Then add data bits
        # Starting with the initial 1
        compressed_byte |= 1 << compressed_bit_pos
        compressed_bit_pos += 1
        if compressed_bit_pos == 8:
            compressed_bit_pos = 0
            output.append(compressed_byte)
            compressed_byte = 0
        # Then proceeding through the number with all the least significant bits
        for j in range(word.bit_length() - 1):
            compressed_byte |= ((word >> j) & 1) << compressed_bit_pos
            compressed_bit_pos += 1
            if compressed_bit_pos == 8:
                compressed_bit_pos = 0
                output.append(compressed_byte)
                compressed_byte = 0
                
    if compressed_bit_pos != 0:
        output.append(compressed_byte)
    
    # Fill in the compressed size, now that we know it
    output[5:7] = len(output).to_bytes(2, 'little')
    
    # return bytes(output)
    return output

def upconvert_palette(pal16):
    assert len(pal16) == 512
    pal24 = bytearray()
    for i in range(0, len(pal16), 2):
        color16 = int.from_bytes(pal16[i:i+2], 'little')
        r = color16 & 0x1F
        g = (color16 >> 5) & 0x1F
        b = (color16 >> 10) & 0x1F
        # Upscale by repeating the bits of the number
        # See also:
        # - https://github.com/higan-emu/emulation-articles/blob/master/video/color-emulation/README.md#color-precision
        # That link doesn't really explain *why* this makes sense though, so...
        # just think of it as a consequence of dealing with very special
        # repeating decimals
        pal24.append(r * 33 >> 2)
        pal24.append(g * 33 >> 2)
        pal24.append(b * 33 >> 2)
    return pal24

def downconvert_palette(pal24):
    assert len(pal24) == 768
    pal16 = bytearray()
    for i in range(0, len(pal24), 3):
        # Since we upconverted by repeating the bits, we can losslessly
        # downconvert by just bit shifting here
        r = pal24[i] >> 3
        g = pal24[i + 1] >> 3
        b = pal24[i + 2] >> 3
        color16 = r | (g << 5) | (b << 10)
        pal16.append(color16 & 0xFF)
        pal16.append(color16 >> 8)
    return pal16

def read_data1(bg_dat, offset):
    # I'm not gonna bother reading the interactive stuff now
    pass

def dump(bg_dat):
    if bg_dat[0:3] != b'SIR':
        raise RuntimeError('File is not a SIR0 or SIR1 file')
    if bg_dat[3:4] != b'0':
        raise RuntimeError('Unsupported SIR{X} version -- only SIR0 (32-bit pointers) is supported for now')

    main_data = int.from_bytes(bg_dat[4:8], 'little')
    # We ignore the pointer metadata because we're cool like that

    num1 = int.from_bytes(bg_dat[main_data:main_data+4], 'little')
    num2 = int.from_bytes(bg_dat[main_data+4:main_data+8], 'little')
    num3 = int.from_bytes(bg_dat[main_data+8:main_data+12], 'little')
    num4 = int.from_bytes(bg_dat[main_data+12:main_data+16], 'little')
    # Not sure if num5 is a number or pointer yet
    num5 = int.from_bytes(bg_dat[main_data+16:main_data+20], 'little')
    assert num5 == 0
    ptr1 = int.from_bytes(bg_dat[main_data+20:main_data+24], 'little')
    ptr2 = int.from_bytes(bg_dat[main_data+24:main_data+28], 'little')
    ptr3 = int.from_bytes(bg_dat[main_data+28:main_data+32], 'little')
    ptr4 = int.from_bytes(bg_dat[main_data+32:main_data+36], 'little')
    assert ptr4 - ptr3 == 512

    structured = {
        'left': num1,
        'top': num2,
        'right': num3,
        'bottom': num4,
        'num5': num5,
        'interactive': None, # read_data1(bg_dat, ptr1) if ptr1 != 0 else None,
        'texture': bg_dat[ptr2:ptr2+((num3 - num1 + 1)*8*(num4 - num2 + 1)*8)],
        'palette': bg_dat[ptr3:ptr3+512],
        'arrangement': None, # read_data4(bg_dat, ptr4, main_data - ptr4)
    }

    return structured

def dump_image(bg_dat):
    # I checked, only AT6P is supported. None of the other three LZ formats.
    if bg_dat[0:4] == b'AT6P':
        bg_dat = at6p_decompress(bg_dat)

    structured = dump(bg_dat)

    width = (structured['right'] - structured['left'] + 1) * 8
    height = (structured['bottom'] - structured['top'] + 1) * 8
    pal = upconvert_palette(structured['palette'])

    image = Image.frombytes('P', (width, height), structured['texture'])
    image.putpalette(pal)
    return image

def replace_image(bg_dat, image, compress=True):
    if image.mode != 'P' and image.mode != 'L':
        raise RuntimeError(f'Image must be indexed or grayscale -- instead found mode "{image.mode}"')
    
    bg_dat_compressed = None
    bg_dat_uncompressed = bytearray(bg_dat)
    if bg_dat[0:4] == b'AT6P':
        bg_dat_compressed = bg_dat
        bg_dat_uncompressed = at6p_decompress(bg_dat)
        
    main_data_offset = int.from_bytes(bg_dat_uncompressed[4:8], 'little')
    left = int.from_bytes(bg_dat_uncompressed[main_data_offset:main_data_offset+4], 'little')
    top = int.from_bytes(bg_dat_uncompressed[main_data_offset+4:main_data_offset+8], 'little')
    right = int.from_bytes(bg_dat_uncompressed[main_data_offset+8:main_data_offset+0xC], 'little')
    bottom = int.from_bytes(bg_dat_uncompressed[main_data_offset+0xC:main_data_offset+0x10], 'little')
    width = (right - left + 1) * 8
    height = (bottom - top + 1) * 8
    if image.width != width or image.height != height:
        raise RuntimeError(f'DAT file reports image size of {width}x{height} ' +
                           f'but provided image has size {image.width}x{image.height}!')
    pixels_offset = int.from_bytes(bg_dat_uncompressed[main_data_offset+0x18:main_data_offset+0x1C], 'little')
    palette_offset = int.from_bytes(bg_dat_uncompressed[main_data_offset+0x1C:main_data_offset+0x20], 'little')
    
    palette = downconvert_palette(image.getpalette())
    
    bg_dat_uncompressed[pixels_offset:pixels_offset+width*height] = list(image.getdata())[:]
    bg_dat_uncompressed[palette_offset:palette_offset+512] = palette
    
    if compress:
        new_compressed = at6p_compress(bg_dat_uncompressed)
        if bg_dat_compressed is not None:
            # Minimize the diff by copying over some of the weird/junk bytes from the old file
            new_compressed[4] = bg_dat_compressed[4]
            new_compressed[8:0x10] = bg_dat_compressed[8:0x10]
            new_compressed[0x15] = bg_dat_compressed[0x15]
        return new_compressed
    else:
        return bg_dat_uncompressed

def print_usage(args):
    print('Usage:')
    print(args[0], 'dump-img <bg.dat> <output.png>')
    print(args[0], 'insert-img <original-bg.dat> <edited.png> <new-bg.dat> [--no-compress]')

def main(args):
    display_encoding = None
    # if len(args) == 5 and args[4].startswith('--display-encoding='):
    #     # Everything after the = sign
    #     display_encoding = args[4][args[4].index('='):]
    # if len(args) == 5 and args[4] == '--ptbr':
    #     display_encoding = 'latin_1'

    if args[1] == 'dump-img':
        if len(args) != 4:
            print_usage(args)
            return 1

        bg_dat = None
        with open(args[2], 'rb') as f:
            bg_dat = f.read()

        image = dump_image(bg_dat)
        image.save(args[3], format='PNG')
    elif args[1] == 'insert-img':
        if len(args) != 5 and len(args) != 6:
            print_usage(args)
            return 1

        no_compress = len(args) == 6 and args[5] == '--no-compress'

        with open(args[2], 'rb') as f:
            bg_dat = f.read()
        with Image.open(args[3], formats=('PNG',)) as edited_image:
            new_dat = replace_image(bg_dat, edited_image, compress = not no_compress)
        with open(args[4], 'wb') as f:
            f.write(new_dat)
    elif args[1] == 'decompress':
        if len(args) != 4:
            print_usage()
            return 1

        with open(args[2], 'rb') as f:
            bg_dat = f.read()
        
        dec = at6p_decompress(bg_dat)
        
        with open(args[3], 'wb') as f:
            f.write(dec)
    elif args[1] == 'compress':
        if len(args) != 4:
            print_usage()
            return 1
        
        with open(args[2], 'rb') as f:
            dec = f.read()
        
        bg_dat = at6p_compress(dec)
        
        with open(args[3], 'wb') as f:
            f.write(bg_dat)
    else:
        print(f'Invalid command "{args[1]}" -- expected "dump-img," "insert-img," "decompress," or "compress"')
        return 1

if __name__ == '__main__':
    exit(main(sys.argv))