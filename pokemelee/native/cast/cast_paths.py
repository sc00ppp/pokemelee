"""Explicit locations for replaying the original character finishing scripts."""
import os
from pathlib import Path

WORK = Path(os.environ["POKEMELEE_CAST_WORK"]).resolve()
TARGETS = Path(os.environ["RIGSWAP_MELEE_TARGETS"]).resolve()
FILES = Path(os.environ["RIGSWAP_MELEE_FILES"]).resolve()


def target_image(fighter, name):
    """Decode one image from the target generated from the user's Melee disc."""
    import io
    import json
    import struct
    from PIL import Image
    data = (TARGETS / f"{fighter}.glb").read_bytes()
    size = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20 + size])
    image = next(i for i in doc["images"] if i.get("name") == name)
    view = doc["bufferViews"][image["bufferView"]]
    start = 28 + size + view.get("byteOffset", 0)
    return Image.open(io.BytesIO(data[start:start + view["byteLength"]])).convert("RGBA")
