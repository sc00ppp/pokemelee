"""Recover both original face texture layers from Gardevoir's PKX."""
from PIL import Image
from cast_paths import WORK
from hsd_scene import Scene, pkx
from hsd_cmpr import cmpr

scene = Scene(pkx("sirnight"))
root = scene.u32(scene.u32(scene.u32(scene.roots["scene_data"])))
images = {tuple(t["size"]): t for j in scene.joints(root) for d in j["dobjs"] for t in d["mobj"]["tobjs"]}
out = WORK / "hand/gardevoir-Peach/look"
for name, size in (("eye", (64, 768)), ("mouth", (64, 384))):
    texture = images[size]
    if texture["fmt"] != 14:
        raise ValueError("Unexpected Gardevoir texture encoding")
    Image.fromarray(cmpr(scene.data[texture["image"]:], *size)).save(out / (name + ".png"))
