"""Restore Machoke's source crest colour after the pinned material exporter.

The loader removes redundant white vertex colours but leaves their shader link.
The exporter loses the composed diffuse colour, writing white. Restore only the
two crest materials after export, preserving geometry and texture addresses used
by the authored team palettes. Low-detail geometry shares these same materials.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys

from pokemelee.datprobe import DatFile, HEADER_SIZE


def restore(costume, source):
    dat = DatFile(costume)
    if hashlib.sha256(dat.raw).hexdigest() != '9eb25a3f8331af2359d7143d05027f03180717b2e380400bb26ae53d10524e20':
        raise ValueError('Machoke must match the reviewed pre-colour export')
    glb = Path(source).read_bytes()
    size = struct.unpack_from('<I', glb, 12)[0]
    model = json.loads(glb[20:20 + size])
    material = next(m for m in model['materials'] if m['name'] == 'goriky_mat_12')
    base = material['pbrMetallicRoughness']
    if 'baseColorTexture' in base:
        raise ValueError('Expected Machoke crest to use a constant source colour')
    rgb = base['baseColorFactor'][:3]
    color = bytes(round(255 * (12.92 * v if v <= .0031308 else 1.055 * v ** (1 / 2.4) - .055))
                  for v in rgb)
    # Reviewed DObjs 10/11: goriky_mat_12 and its mirrored surface. These are
    # material-structure offsets, relative to the DAT data section.
    data = bytearray(dat.raw)
    for offset in (0x2645c, 0x26528):
        at = HEADER_SIZE + offset + 4
        if data[at:at + 3] != b'\xff\xff\xff':
            raise ValueError('Machoke crest material layout changed')
        data[at:at + 3] = color
    Path(costume).write_bytes(data)
    print('Restored Machoke crest from source material:', color.hex(), flush=True)


if __name__ == '__main__':
    restore(*sys.argv[1:3])
