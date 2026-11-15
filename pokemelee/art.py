"""Rebuild Colosseum stock icons and party-face fallback icons from a disc.

Adapted from the existing colo_art.py recipe. This is not the final rendered
3D CSS portrait recipe used by Cast Test 30.
"""
import io
import struct

import numpy as np
from PIL import Image

from .fsys import entries
from .workspace import digest, output_directory, receipt, write_blob

ARCHIVES = ("poke_face.fsys", "poke_body.fsys", "pocket_menu.fsys")


def rgb5a3(value):
    if value & 0x8000:
        r, g, b = (value >> 10) & 31, (value >> 5) & 31, value & 31
        return (r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2, 255)
    return ((value >> 8 & 15) * 17, (value >> 4 & 15) * 17,
            (value & 15) * 17, (value >> 12 & 7) * 255 // 7)


def decode(blob):
    if len(blob) < 0x80:
        raise ValueError("Truncated Colosseum texture header")
    w, h, bpp = struct.unpack_from(">HHB", blob)
    if not 0 < w <= 4096 or not 0 < h <= 4096 or bpp not in (16, 32):
        raise ValueError(f"Unsupported Colosseum texture: {w}x{h}, {bpp} bpp")
    pw, ph = (w + 3) // 4 * 4, (h + 3) // 4 * 4
    if len(blob) < 0x80 + pw * ph * bpp // 8:
        raise ValueError("Truncated Colosseum texture data")
    result = np.zeros((ph, pw, 4), np.uint8)
    at = 0x80
    for y in range(0, ph, 4):
        for x in range(0, pw, 4):
            if bpp == 32:
                tile = blob[at:at + 64]
                for i in range(16):
                    result[y + i // 4, x + i % 4] = (tile[2*i+1], tile[32+2*i], tile[33+2*i], tile[2*i])
                at += 64
            else:
                for i in range(16):
                    result[y + i // 4, x + i % 4] = rgb5a3(struct.unpack_from(">H", blob, at)[0])
                    at += 2
    return Image.fromarray(result[:h, :w])


def one(archive, suffix):
    matches = [blob for name, blob in archive.items() if name.endswith("_" + suffix + ".t12")]
    if len(matches) != 1:
        raise ValueError(f"Expected one {suffix} texture; found {len(matches)}")
    return decode(matches[0])


def css_icon(face, panel):
    frame = np.array(panel.crop((247, 5, 305, 63)))
    frame = np.delete(np.delete(frame, [28, 29], axis=0), [28, 29], axis=1)
    pic = Image.new("RGBA", (56, 56))
    pic.alpha_composite(face.crop((1, 1, 41, 41)), (8, 8))
    pic.alpha_composite(Image.fromarray(frame))
    out = Image.new("RGBA", (64, 56))
    out.alpha_composite(pic, (4, 0))
    return out


def stock_icon(im):
    box = im.getbbox()
    if box is None:
        raise ValueError("Empty stock icon")
    x0, y0, x1, y1 = box
    side = max(x1 - x0, y1 - y0)
    sq = Image.new("RGBA", (side, side))
    sq.alpha_composite(im.crop(box), ((side - x1 + x0) // 2, (side - y1 + y0) // 2))
    px = np.array(sq)
    solid = px[..., 3] > 127
    if not solid.any():
        raise ValueError("Stock icon has no opaque pixels")
    palette = Image.fromarray(px[solid][None, :, :3]).quantize(
        15, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    rgb = np.array(Image.fromarray(px[..., :3]).quantize(palette=palette, dither=Image.Dither.NONE).convert("RGB"))
    return Image.fromarray(np.dstack([rgb, solid * 255]).astype(np.uint8))


def generate(disc, output, indices):
    indices = sorted(set(indices))
    if not indices or any(not i.rstrip("x").isdigit() or len(i) > 4 for i in indices):
        raise ValueError("Use Gen 3 internal art indices such as 025, 307 or 201x")
    sources, archives = [], {}
    for name in ARCHIVES:
        data = disc.read(name)
        sources.append({"disc_file": name, "bytes": len(data), "sha256": digest(data)})
        archives[name] = dict(entries(data))
    panel = one(archives["pocket_menu.fsys"], "menu006")
    outputs = []
    with output_directory(output, "menu-art") as root:
        for index in indices:
            images = {
                f"css-{index}.png": css_icon(one(archives["poke_face.fsys"], f"face{index}"), panel),
                f"stock-{index}.png": stock_icon(one(archives["poke_body.fsys"], f"body{index}")),
            }
            for name, im in images.items():
                buffer = io.BytesIO()
                im.save(buffer, format="PNG")
                outputs.append(write_blob(root, name, buffer.getvalue()))
        return receipt(root, "menu-art", {"disc": disc.info(), "files": sources}, outputs,
                       note="Stock icons and party-face fallback CSS icons, not the final 3D CSS portraits")
