# MODEL (todo: rename)
# for 999: Nine Hours, Nine Persons, Nine Doors (DS)
# by PhoenixBound
# Last updated: 2026-02-28

import json
import math
from pathlib import Path
import struct
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

def atxp_decompress(data):
    if data[0:4] == b'AT6P':
        return at6p_decompress(data)

    if data[0:4] == b'AT5P':
        compressed_size = data[5] | (data[6] << 8) | (data[0x13] << 16)
        decompressed_size = int.from_bytes(data[0x10:0x13], 'little')
        i = 0x14
    elif data[0:4] == b'AT4P':
        compressed_size = int.from_bytes(data[5:7], 'little')
        decompressed_size = int.from_bytes(data[0x10:0x12], 'little')
        i = 0x12
    elif data[0:4] == b'AT3P':
        compressed_size = int.from_bytes(data[5:7], 'little')
        decompressed_size = 0x7FFFFFFF
        i = 7

    if data[4] == ord('N'):
        return data[7:7+compressed_size]

    nybble_list = data[7:16]
    assert compressed_size == len(data)
    flags = data[i]
    i += 1
    flags_read = 0
    dest = bytearray()
    while i < compressed_size:
        if flags_read == 8:
            flags = data[i]
            i += 1
            flags_read = 0

        if (flags & 0x80) != 0:
            # Literal byte
            dest.append(data[i])
            i += 1
        else:
            length = data[i] >> 4
            cmd = nybble_list.find(length.to_bytes(1, 'little'))
            if cmd == -1:
                # LZ pointer reference
                length += 3
                offset = ((data[i] & 0xF) << 8) | data[i + 1]
                for _ in range(length):
                    dest.append(dest[len(dest) - 4096 + offset])
                i += 2
            else:
                n = data[i] & 0xF
                h = (n + 1) & 0xF
                l = (n - 1) & 0xF
                if cmd == 0:
                    dest.append(n * 0x11)
                    dest.append(n * 0x11)
                elif cmd == 1:
                    dest.append((n << 4) | h)
                    dest.append(h * 0x11)
                elif cmd == 2:
                    dest.append((n << 4) | l)
                    dest.append(n * 0x11)
                elif cmd == 3:
                    dest.append(n * 0x11)
                    dest.append((l << 4) | n)
                elif cmd == 4:
                    dest.append(n * 0x11)
                    dest.append((n << 4) | l)
                elif cmd == 5:
                    dest.append((n << 4) | l)
                    dest.append(l * 0x11)
                elif cmd == 6:
                    dest.append((n << 4) | h)
                    dest.append(n * 0x11)
                elif cmd == 7:
                    dest.append(n * 0x11)
                    dest.append((h << 4) | n)
                else:
                    dest.append(n * 0x11)
                    dest.append((n << 4) | h)
                i += 1
        flags_read += 1
        flags <<= 1
    assert decompressed_size == len(dest)
    return dest

def upconvert_palette(pal16, alpha=False):
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
        if alpha:
            if i == 0:
                pal24.append(0)
            else:
                pal24.append(0xFF)
            
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

def read_texture_list(item_b3d, offset, count):
    texture_dict = {}
    for _ in range(count):
        texture_ptr = int.from_bytes(item_b3d[offset:offset+4], 'little')
        offset += 4
        
        name_ptr = int.from_bytes(item_b3d[texture_ptr:texture_ptr+4], 'little')
        # Is this one field? Two fields? A pointer? A number?
        unk4 = int.from_bytes(item_b3d[texture_ptr+4:texture_ptr+8], 'little')
        assert unk4 == 0
        palette_ptr = int.from_bytes(item_b3d[texture_ptr+8:texture_ptr+12], 'little')
        gfx_ptr = int.from_bytes(item_b3d[texture_ptr+12:texture_ptr+16], 'little')
        s_size = int.from_bytes(item_b3d[texture_ptr+16:texture_ptr+18], 'little', signed=True)
        t_size = int.from_bytes(item_b3d[texture_ptr+18:texture_ptr+20], 'little', signed=True)
        
        assert (s_size & 0xFFF8) == 0
        assert (t_size & 0xFFF8) == 0
        width = 1 << (3 + s_size)
        height = 1 << (3 + t_size)

        name = read_str(item_b3d, name_ptr)
        assert name not in texture_dict
        
        texture_dict[name] = {\
            'name': name,\
            'unk4': unk4,\
            'palette': item_b3d[palette_ptr:palette_ptr+0x200],\
            'gfx': item_b3d[gfx_ptr:gfx_ptr+width*height],\
            'width': width,\
            'height': height,\
        }
    return texture_dict

def read_material_list(item_b3d, offset, count, texture_dict):
    material_dict = {}
    for _ in range(count):
        material_ptr = int.from_bytes(item_b3d[offset:offset+4], 'little')
        offset += 4
        
        name_ptr = int.from_bytes(item_b3d[material_ptr:material_ptr+4], 'little')
        texture_ptr = int.from_bytes(item_b3d[material_ptr+4:material_ptr+8], 'little')
        unused_color = int.from_bytes(item_b3d[material_ptr+8:material_ptr+12], 'big')
        ambient_color = int.from_bytes(item_b3d[material_ptr+12:material_ptr+16], 'big')
        emission_color = int.from_bytes(item_b3d[material_ptr+16:material_ptr+20], 'big')
        
        name = read_str(item_b3d, name_ptr)
        assert name not in material_dict
        
        texture_name = None
        if texture_ptr:
            texture_name_ptr = int.from_bytes(item_b3d[texture_ptr:texture_ptr+4], 'little')
            texture_name = read_str(item_b3d, texture_name_ptr)
            assert texture_name in texture_dict
        
        # All of these colors are in RGBx format. Verify that the x padding would be 0xFF
        assert (unused_color & 0xFF) == 0xFF
        assert (ambient_color & 0xFF) == 0xFF
        assert (emission_color & 0xFF) == 0xFF
        
        # Please I don't want to figure out how to dump a material with an ambient color set
        assert (ambient_color >> 8) == 0
        
        material_dict[name] = {\
            'name': name,\
            'texture': texture_name,\
            'unused': f'#{unused_color >> 8:06x}',\
            'ambient': f'#{ambient_color >> 8:06x}',\
            'emission': f'#{emission_color >> 8:06x}',\
        }
    
    return material_dict

def read_face_list(item_b3d, offset, count):
    faces = []
    for _ in range(count):
        vertex_count = int.from_bytes(item_b3d[offset:offset+2], 'little')
        offset += 2
        assert vertex_count == 3 or vertex_count == 4
        
        face = []
        for _ in range(vertex_count):
            x = int.from_bytes(item_b3d[offset:offset+2], 'little', signed=True)
            y = int.from_bytes(item_b3d[offset+2:offset+4], 'little', signed=True)
            z = int.from_bytes(item_b3d[offset+4:offset+6], 'little', signed=True)
            normal_x = int.from_bytes(item_b3d[offset+6:offset+8], 'little', signed=True)
            normal_y = int.from_bytes(item_b3d[offset+8:offset+10], 'little', signed=True)
            normal_z = int.from_bytes(item_b3d[offset+10:offset+12], 'little', signed=True)
            s = int.from_bytes(item_b3d[offset+12:offset+14], 'little', signed=True)
            t = int.from_bytes(item_b3d[offset+14:offset+16], 'little', signed=True)
            offset += 0x10
            
            # Full precision
            x /= 0x1000
            y /= 0x1000
            z /= 0x1000
            # Given 3 extra fractional digits to look like the normal X/Y/Z coords
            # (REG_NORMAL has 9 fractional bits)
            normal_x /= 0x1000
            normal_y /= 0x1000
            normal_z /= 0x1000
            # Funnily, the texture coordinates are integers, not fixed point numbers with 4 fractional bits.
            assert (s >> 12) == (s >> 15)
            assert (t >> 12) == (t >> 15)
            
            face.append({\
                'pos': [x, y, z],\
                'normal': [normal_x, normal_y, normal_z],\
                'tex_coords': [s, t],\
            })

        faces.append(face)
    
    return faces

def read_mesh_primitive_list(item_b3d, offset, count, material_dict):
    primitives_list = []
    
    for _ in range(count):
        primitive_ptr = int.from_bytes(item_b3d[offset:offset+4], 'little')
        offset += 4
        
        material_ptr = int.from_bytes(item_b3d[primitive_ptr:primitive_ptr+4], 'little')
        face_count = int.from_bytes(item_b3d[primitive_ptr+4:primitive_ptr+6], 'little', signed=True)
        padding = int.from_bytes(item_b3d[primitive_ptr+6:primitive_ptr+8], 'little')
        face_list_ptr = int.from_bytes(item_b3d[primitive_ptr+8:primitive_ptr+12], 'little')
        
        assert padding == 0xAAAA
        
        # Hopefully all models put all their materials in the material list.
        # There's nothing in the actual game that seems to read from the list, so it's mainly
        # there for tool convenience, I guess.
        material_name = None
        if material_ptr:
            material_name_ptr = int.from_bytes(item_b3d[material_ptr:material_ptr+4], 'little')
            material_name = read_str(item_b3d, material_name_ptr)
            assert material_name in material_dict
        
        primitives_list.append({\
            'material': material_name,\
            'faces': read_face_list(item_b3d, face_list_ptr, face_count),\
        })
    return primitives_list

def read_mesh_list(item_b3d, offset, count, material_dict):
    mesh_list = []
    for _ in range(count):
        mesh_ptr = int.from_bytes(item_b3d[offset:offset+4], 'little')
        offset += 4
        
        name_ptr = int.from_bytes(item_b3d[mesh_ptr:mesh_ptr+4], 'little')
        x_scale = int.from_bytes(item_b3d[mesh_ptr+4:mesh_ptr+6], 'little', signed=True)
        y_scale = int.from_bytes(item_b3d[mesh_ptr+6:mesh_ptr+8], 'little', signed=True)
        z_scale = int.from_bytes(item_b3d[mesh_ptr+8:mesh_ptr+10], 'little', signed=True)
        x_rot = int.from_bytes(item_b3d[mesh_ptr+10:mesh_ptr+12], 'little', signed=True)
        y_rot = int.from_bytes(item_b3d[mesh_ptr+12:mesh_ptr+14], 'little', signed=True)
        z_rot = int.from_bytes(item_b3d[mesh_ptr+14:mesh_ptr+16], 'little', signed=True)
        x_pos = int.from_bytes(item_b3d[mesh_ptr+16:mesh_ptr+18], 'little', signed=True)
        y_pos = int.from_bytes(item_b3d[mesh_ptr+18:mesh_ptr+20], 'little', signed=True)
        z_pos = int.from_bytes(item_b3d[mesh_ptr+20:mesh_ptr+22], 'little', signed=True)
        primitive_count = int.from_bytes(item_b3d[mesh_ptr+22:mesh_ptr+24], 'little')
        primitive_list_ptr = int.from_bytes(item_b3d[mesh_ptr+24:mesh_ptr+28], 'little')
                
        name = read_str(item_b3d, name_ptr)
        x_scale /= 0x1000
        y_scale /= 0x1000
        z_scale /= 0x1000
        x_pos /= 0x1000
        y_pos /= 0x1000
        z_pos /= 0x1000
        # For now, store rotation angles in "turns" (1.0 = 180 degrees)
        x_rot /= 0x8000
        y_rot /= 0x8000
        z_rot /= 0x8000
        
        mesh_list.append({\
            'name': name,\
            'scale': [x_scale, y_scale, z_scale],\
            'rotation': [x_rot, y_rot, z_rot],\
            'position': [x_pos, y_pos, z_pos],\
            'primitives': read_mesh_primitive_list(item_b3d, primitive_list_ptr, primitive_count, material_dict),\
        })

    return mesh_list

def dump(item_b3d):
    if item_b3d[0:3] != b'SIR':
        item_b3d = atxp_decompress(item_b3d)
        if item_b3d[0:3] != b'SIR':
            raise RuntimeError('File is not a SIR0 or SIR1 file')
    if item_b3d[3:4] != b'0':
        raise RuntimeError('Unsupported SIR{X} version -- only SIR0 (32-bit pointers) is supported for now')

    main_data = int.from_bytes(item_b3d[4:8], 'little')
    # We ignore the pointer metadata because we're cool like that

    magic = item_b3d[main_data:main_data+4].decode('ascii')
    # TODO: support v101 if there are models in that format in 999
    assert magic == 'v102'
    x_pos = int.from_bytes(item_b3d[main_data+4:main_data+6], 'little', signed=True)
    y_pos = int.from_bytes(item_b3d[main_data+6:main_data+8], 'little', signed=True)
    z_pos = int.from_bytes(item_b3d[main_data+8:main_data+10], 'little', signed=True)
    count1 = int.from_bytes(item_b3d[main_data+10:main_data+12], 'little', signed=True)
    count2 = int.from_bytes(item_b3d[main_data+12:main_data+14], 'little', signed=True)
    count3 = int.from_bytes(item_b3d[main_data+14:main_data+16], 'little', signed=True)
    count4 = int.from_bytes(item_b3d[main_data+16:main_data+18], 'little', signed=True)
    count5 = int.from_bytes(item_b3d[main_data+18:main_data+20], 'little', signed=True)
    ptr1 = int.from_bytes(item_b3d[main_data+20:main_data+24], 'little')
    ptr2 = int.from_bytes(item_b3d[main_data+24:main_data+28], 'little')
    ptr3 = int.from_bytes(item_b3d[main_data+28:main_data+32], 'little')
    ptr4 = int.from_bytes(item_b3d[main_data+32:main_data+36], 'little')
    ptr5 = int.from_bytes(item_b3d[main_data+36:main_data+40], 'little')
    
    texture_dict = read_texture_list(item_b3d, ptr1, count1)
    material_dict = read_material_list(item_b3d, ptr2, count2, texture_dict)
    mesh_list = read_mesh_list(item_b3d, ptr3, count3, material_dict)
    
    texture_list = list(texture_dict.values())
    material_list = list(material_dict.values())
    
    assert count4 == 0
    assert count5 == 0

    structured = {
        'magic': magic,
        'x_pos': x_pos / 0x1000,
        'y_pos': y_pos / 0x1000,
        'z_pos': z_pos / 0x1000,
        'textures': texture_list,
        'materials': material_list,
        'meshes': mesh_list,
        # TODO: there's code for accessing these. They're probably animation related?
        'unk20': [],
        'unk24': [],
    }

    return structured

def srgb_channel_to_linear(c):
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4

def srgb_string_to_linear(color):
    assert color[0] == '#'
    assert len(color) == 7
    color_int = int(color[1:7], 16)
    red = (color_int >> 16) / 255
    green = ((color_int >> 8) & 0xFF) / 255
    blue = (color_int & 0xFF) / 255

    r = srgb_channel_to_linear(red)
    g = srgb_channel_to_linear(green)
    b = srgb_channel_to_linear(blue)
    return [r, g, b]

def euler_to_quaternion(euler):
    """
    x, y, and z should be in turns (1 turn = 180 degrees = pi radians).
    The returned quaternion should be in glTF format (XYZW order, where W is the scalar)
    glTF uses a right-handed coordinate system where Y is up and the object is oriented to face in the Z direction.
    Unsure about the DS/999's conventions... It follows lab 1-2-3 order/Body 3-2-1 order, at least.
    """
    x = euler[0]
    y = euler[1]
    z = euler[2]
    # https://en.wikipedia.org/wiki/Conversion_between_quaternions_and_Euler_angles#Euler_angles_(in_3-2-1_sequence)_to_quaternion_conversion
    # We'll deal with fixing the axes at a later time
    
    # If you're rewriting this in C, use sinpi/cospi here for greater accuracy
    # The short variable names here refer to cosine/sine of roll/pitch/yaw,
    # per Wikipedia example code
    cr = math.cos(x * 0.5 * math.pi)
    sr = math.sin(x * 0.5 * math.pi)
    cp = math.cos(y * 0.5 * math.pi)
    sp = math.sin(y * 0.5 * math.pi)
    cy = math.cos(z * 0.5 * math.pi)
    sy = math.sin(z * 0.5 * math.pi)
    
    qw = cr * cp * cy + sr * sp * sy
    qx = sr * cp * cy - cr * sp * sy
    qy = cr * sp * cy + sr * cp * sy
    qz = cr * cp * sy - sr * sp * cy
    
    return [qx, qy, qz, qw]

def split_up_accessor_data(mesh_primitive, s_size, t_size):
    positions = bytearray()
    normals = bytearray()
    texcoords = bytearray()
    
    pos_min = [math.inf, math.inf, math.inf]
    pos_max = [-math.inf, -math.inf, -math.inf]
    
    for face in mesh_primitive['faces']:
        # Preprocess all vertices in the face to convert them to bytes *once*
        # All three components of position/normal data get put in the same bytes object
        # (same for both components of the texture coordinates)
        # Also swap the X and Z coordinates here to make the coordinates left-handed
        verts = []
        for vertex in face:
            x = vertex['pos'][0]
            y = vertex['pos'][1]
            z = vertex['pos'][2]
            nx = vertex['normal'][0]
            ny = vertex['normal'][1]
            nz = vertex['normal'][2]
            s = vertex['tex_coords'][0]
            t = vertex['tex_coords'][1]
            
            x, z = z, x
            nx, nz = nz, nx
            
            verts.append((\
                struct.pack('<fff', x, y, z),\
                struct.pack('<fff', nx, ny, nz),\
                struct.pack('<ff', s / s_size, t / t_size), \
            ))
            
            pos_min[0] = min(pos_min[0], x)
            pos_min[1] = min(pos_min[1], y)
            pos_min[2] = min(pos_min[2], z)
            pos_max[0] = max(pos_max[0], x)
            pos_max[1] = max(pos_max[1], y)
            pos_max[2] = max(pos_max[2], z)

        # Attempt to make the model not inside-out
        verts.reverse()
        
        # Split up quads into triangles and append the triangles
        # TODO: switch to the algorithm used by MikkTSpace...? What does it help with?
        positions.extend(verts[0][0])
        positions.extend(verts[1][0])
        positions.extend(verts[2][0])
        normals.extend(verts[0][1])
        normals.extend(verts[1][1])
        normals.extend(verts[2][1])
        texcoords.extend(verts[0][2])
        texcoords.extend(verts[1][2])
        texcoords.extend(verts[2][2])
        if len(verts) != 3:
            positions.extend(verts[2][0])
            positions.extend(verts[3][0])
            positions.extend(verts[0][0])
            normals.extend(verts[2][1])
            normals.extend(verts[3][1])
            normals.extend(verts[0][1])
            texcoords.extend(verts[2][2])
            texcoords.extend(verts[3][2])
            texcoords.extend(verts[0][2])
            

    return (positions, normals, texcoords, pos_min, pos_max)

def make_gltf(structured, gltf_name):
    gltf = {'asset':{'version': '2.0', 'generator': 'Chunsoft B3D v102 model converter by PhoenixBound'}}
    gltf['scene'] = 0
    gltf['scenes'] = [{'name': gltf_name, 'nodes': [0]}]
    gltf['nodes'] = []
    root_node = {\
        'name': 'Model', \
        'translation': [structured['x_pos'], structured['y_pos'], structured['z_pos']], \
    }
    gltf['nodes'].append(root_node)
    
    gltf_buffer_data = bytearray()
    gltf['buffers'] = [{\
        'uri': 'model.glbin',\
    }]
    
    if structured['textures']:
        images = []
        textures = []
        
        for (i, tex) in enumerate(structured['textures']):
            images.append({'uri': tex['name'] + '.png'})
            textures.append({'name': tex['name'], 'sampler': 0, 'source': i})
        
        gltf['samplers'] = [\
            {\
                # Nearest neighbor texture resampling
                'magFilter': 9728,\
                'minFilter': 9728,\
                # Clamp to edge
                'wrapS': 33071,\
                'wrapT': 33071,\
            }\
        ]
        gltf['images'] = images
        gltf['textures'] = textures
    
    if structured['materials']:
        materials = []
        for (i, mat) in enumerate(structured['materials']):
            # Find the texture we want
            tex_idx = None
            tex_name = mat['texture']
            if tex_name:
                for (j, t) in enumerate(gltf['textures']):
                    if 'name' in t and t['name'] == tex_name:
                        tex_idx = j
                        break
                else:
                    raise RuntimeError(f'Texture "{tex_name}" not found')

            gltf_mat = {\
                'name': mat['name'],\
                'pbrMetallicRoughness': {\
                    'metallicFactor': 0,\
                    'roughnessFactor': 1,\
                },\
                'alphaMode': 'MASK',\
            }
            
            if tex_idx is not None:
                gltf_mat['pbrMetallicRoughness']['baseColorTexture'] = {\
                    'index': tex_idx,\
                    'texCoord': i,\
                }
            
            # This defaults to gray
            # Should (1 - this color) in grayscale be treated as the occlusion texture instead...?
            # Or maybe I should give up and put it in extras?
            ambient_color = mat['ambient']
            if ambient_color != '#000000':
                gltf_mat['pbrMetallicRoughness']['baseColorFactor'] = srgb_string_to_linear(ambient_color)
            del ambient_color
            
            emission_color = mat['emission']
            if emission_color != '#000000':
                gltf_mat['emissiveFactor'] = srgb_string_to_linear(emission_color)
            del emission_color
            
            materials.append(gltf_mat)

        gltf['materials'] = materials

    if structured['meshes']:
        meshes = []
        if ('children' not in root_node) and structured['meshes']:
            root_node['children'] = []
        # This isn't strictly correct but I don't care I want to be done with this...
        if 'accessors' not in gltf:
            gltf_accessors = []
            gltf['accessors'] = gltf_accessors
        if 'bufferViews' not in gltf:
            gltf_buffer_views = []
            gltf['bufferViews'] = gltf_buffer_views
        if 'buffers' not in gltf:
            gltf['buffers'] = []

        
        for (i, mesh) in enumerate(structured['meshes']):
            primitives = []

            for mesh_primitive in mesh['primitives']:
                # Sort out the material info
                material_idx = None
                material_name = mesh_primitive['material']
                if material_name:
                    for (j, m) in enumerate(gltf['materials']):
                        if 'name' in m and m['name'] == material_name:
                            material_idx = j
                            break
                    else:
                        raise RuntimeError(f'Material "{material_name}" not found')

                # And texture size info, since we need that to fix texture coordinates...
                s_size = None
                t_size = None
                structured_material = None
                for m in structured['materials']:
                    if m['name'] == material_name:
                        structured_material = m
                        break
                structured_texture = None
                texture_name = structured_material['texture']
                if texture_name is not None:
                    for tex in structured['textures']:
                        if tex['name'] == texture_name:
                            structured_texture = tex
                            break
                    s_size = structured_texture['width']
                    t_size = structured_texture['height']
                del structured_material
                del structured_texture
                del texture_name
                
                (positions, normals, texcoords, pos_min, pos_max) = split_up_accessor_data(mesh_primitive, s_size, t_size)
                
                positions_accessor = len(gltf_accessors)
                gltf_accessors.append({\
                    'bufferView': len(gltf_buffer_views),\
                    # float
                    'componentType': 5126,\
                    'type': 'VEC3',\
                    'count': len(positions) // 12,\
                    'min': pos_min,\
                    'max': pos_max,\
                })
                gltf_buffer_views.append({\
                    'buffer': 0,\
                    'byteLength': len(positions),\
                    'byteOffset': len(gltf_buffer_data),\
                    # ARRAY_BUFFER
                    'target': 34962
                })
                gltf_buffer_data.extend(positions)
                
                normals_accessor = len(gltf_accessors)
                gltf_accessors.append({\
                    'bufferView': len(gltf_buffer_views),\
                    # float
                    'componentType': 5126,\
                    'type': 'VEC3',\
                    'count': len(normals) // 12,\
                })
                gltf_buffer_views.append({\
                    'buffer': 0,\
                    'byteLength': len(normals),\
                    'byteOffset': len(gltf_buffer_data),\
                    # ARRAY_BUFFER
                    'target': 34962
                })
                gltf_buffer_data.extend(normals)
                
                texcoords_accessor = len(gltf_accessors)
                gltf_accessors.append({\
                    'bufferView': len(gltf_buffer_views),\
                    # float
                    'componentType': 5126,\
                    'type': 'VEC2',\
                    'count': len(texcoords) // 8,\
                })
                gltf_buffer_views.append({\
                    'buffer': 0,\
                    'byteLength': len(texcoords),\
                    'byteOffset': len(gltf_buffer_data),\
                    # ARRAY_BUFFER
                    'target': 34962
                })
                gltf_buffer_data.extend(texcoords)
                
                gltf_primitive = {\
                    'attributes': {\
                        'POSITION': positions_accessor,\
                        'NORMAL': normals_accessor,\
                    },\
                }
                if material_idx is not None:
                    gltf_primitive['material'] = material_idx
                    gltf_primitive['attributes'][f'TEXCOORD_{material_idx}'] = texcoords_accessor
                    
                primitives.append(gltf_primitive)
            
            gltf_mesh = {'primitives': primitives}
            meshes.append(gltf_mesh)
            
            gltf_mesh_node = {\
                'name': mesh['name'],\
                'scale': mesh['scale'],\
                'rotation': euler_to_quaternion(mesh['rotation']),\
                'translation': mesh['position'],\
                'mesh': i,\
            }
            root_node['children'].append(len(gltf['nodes']))
            gltf['nodes'].append(gltf_mesh_node)
            
        gltf['meshes'] = meshes
        
    gltf['buffers'][0]['byteLength'] = len(gltf_buffer_data)
    
    return gltf, gltf_buffer_data

def print_usage(args):
    print('Usage:')
    print(args[0], 'dump <model.b3d> <output-dir>')
    print(args[0], 'decompress <compressed.b3d> <output.b3d>')

def main(args):
    display_encoding = None
    # if len(args) == 5 and args[4].startswith('--display-encoding='):
    #     # Everything after the = sign
    #     display_encoding = args[4][args[4].index('='):]
    # if len(args) == 5 and args[4] == '--ptbr':
    #     display_encoding = 'latin_1'

    if args[1] == 'dump':
        if len(args) != 4:
            print_usage(args)
            return 1

        item_b3d = None
        with open(args[2], 'rb') as f:
            item_b3d = f.read()

        structured = dump(item_b3d)
        out_folder = Path(args[3])
        out_folder.mkdir(exist_ok=True)

        for texture in structured['textures']:
            width = texture['width']
            height = texture['height']
            gfx = texture['gfx']
            
            pal = upconvert_palette(texture['palette'], alpha=True)            
            
            # del texture['width']
            # del texture['height']
            # del texture['gfx']
            # del texture['palette']
            
            image = Image.frombytes('P', (width, height), gfx)
            image.putpalette(pal, rawmode='RGBA')
            image.save(out_folder / (texture['name'] + '.png'))

        gltf, buffer_data = make_gltf(structured, out_folder.name)

        # with open(out_folder / 'raw_model.json', 'w', encoding='utf-8', newline='\n') as f:
        #     json.dump(structured, f, ensure_ascii=False, indent=4)
            
        with open(out_folder / 'model.gltf', 'w', encoding='utf-8', newline='\n') as f:
            json.dump(gltf, f)
        
        with open(out_folder / 'model.glbin', 'wb') as f:
            f.write(buffer_data)
    # elif args[1] == 'insert-img':
    #     if len(args) != 5 and len(args) != 6:
    #         print_usage(args)
    #         return 1

    #     no_compress = len(args) == 6 and args[5] == '--no-compress'

    #     with open(args[2], 'rb') as f:
    #         bg_dat = f.read()
    #     with Image.open(args[3], formats=('PNG',)) as edited_image:
    #         new_dat = replace_image(bg_dat, edited_image, compress = not no_compress)
    #     with open(args[4], 'wb') as f:
    #         f.write(new_dat)
    elif args[1] == 'decompress':
        if len(args) != 4:
            print_usage()
            return 1

        with open(args[2], 'rb') as f:
            bg_dat = f.read()
        
        dec = atxp_decompress(bg_dat)
        
        with open(args[3], 'wb') as f:
            f.write(dec)
    elif args[1] == 'compress':
        if len(args) != 4:
            print_usage()
            return 1
        
        with open(args[2], 'rb') as f:
            dec = f.read()
        
        raise NotImplementedError()
        bg_dat = at6p_compress(dec)
        
        with open(args[3], 'wb') as f:
            f.write(bg_dat)
    else:
        print(f'Invalid command "{args[1]}" -- expected "dump," "decompress," or "compress"')
        return 1

if __name__ == '__main__':
    exit(main(sys.argv))
