"""Replay saved cast decisions through the pinned geometry helpers.

This worker deliberately has no agent entry point or decision callback. Recipes
contain authored bone roles, visibility and eye-frame choices, never model data.
"""
from __future__ import annotations

import importlib.abc
import json
import sys
from pathlib import Path


class OfflineImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"rigswap.ai", "rigswap.core.run", "rigswap.pipeline"}:
            raise RuntimeError(f"Authoring entry point forbidden in a fixed build: {fullname}")


def no_network(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.bind"}:
        raise RuntimeError("Character recipe workers run offline")


sys.meta_path.insert(0, OfflineImports())
sys.addaudithook(no_network)


def size_to_target(rig, shape, frig, description, objects, fighter_meshes):
    from rigswap.core import body, correspond, onepiece, segments
    fch = correspond.fighter_chains(frig, description)
    mch = correspond.model_chains(rig, shape)[0]
    levels = correspond.levels(mch)
    if shape.plan == "ball" or correspond.fighter_plan(description) == "ball" or levels[2] <= levels[1]:
        k = fch["spine"].end[2] / mch["spine"].end[2]
        if body.FIX.get("size") != "top":
            def room(meshes):
                return onepiece.room(*segments._surface(segments._meshes(meshes))[:2])
            k = min(k, (room(fighter_meshes) / room(objects)) ** (1 / 3))
        return k
    return correspond.levels(fch, fighter=True)[2] / levels[2]


def head_weights(rig, shape):
    import bpy
    import numpy as np
    from rigswap.core import correspond
    spine = correspond.model_chains(rig, shape)[0]["spine"]
    below = [spine.bones[min(spine.anchors[1] + 1, spine.anchors[2])]]
    kids = rig.children()
    for b in below:
        below += kids[b]
    share = rig.weights[:, below].sum(axis=1)
    counts = [len(bpy.data.objects[n].data.vertices) for n in rig.meshes]
    return {n: share[a:a + count] for n, a, count in zip(rig.meshes, np.cumsum([0] + counts), counts)}


def replay_eyes(build_dir, head, recipe, source):
    import bpy
    from rigswap.core import eyes
    if recipe.get("skip"):
        return eyes._write(build_dir, {"skipped": recipe["skip"]})
    surfaces, _ = eyes.candidates(head)
    expected = recipe["surfaces"]
    actual = {str(s.n): s.key for s in surfaces}
    if actual != expected:
        raise ValueError(f"Eye surface inventory changed: {actual!r} != {expected!r}")
    selected = [s for s in surfaces if s.n in recipe["selected"]]
    pixels = {s.image: eyes._pixels(bpy.data.images[s.image]) for s in surfaces}
    if recipe.get("fixed"):
        made = eyes.make_fixed(build_dir, selected, pixels, recipe["fixed"])
    else:
        found = eyes.others(surfaces, pixels, source)
        chosen = {}
        for state in ("half", "closed"):
            chosen[state] = []
            for expected_frame in recipe.get(state, []):
                matches = [f for f in found if all(f[k] == v for k, v in expected_frame.items())]
                if len(matches) != 1:
                    raise ValueError(f"Saved {state} eye frame no longer resolves: {expected_frame}")
                chosen[state].append(matches[0])
        made = eyes.make(build_dir, selected, chosen, pixels, source)
    if not made.get("objects"):
        raise ValueError(f"Saved eye recipe produced no eyes: {made}")
    bpy.ops.wm.save_as_mainfile(filepath=str(build_dir / "build.blend"))
    return eyes._write(build_dir, made)


def replay(recipe, model, targets, out):
    import bpy
    import numpy as np
    from rigswap.load.open import run as load_model
    from rigswap.core import body, build, cloth, correspond, hang, paint, repose, rig as rigs, variants
    from rigswap.plugins.melee.targets.bones import item_joints
    from rigswap.plugins.melee.targets.weapons import read_weapons

    out.mkdir(parents=True, exist_ok=False)
    load_dir = out / "1-load"
    listing = load_model(model, load_dir)
    if len(listing) != 1 or not listing[0].get("opened") or not listing[0].get("skinned"):
        raise ValueError("Expected exactly one rigged Colosseum model")
    rig = rigs.read(load_dir / "models" / listing[0]["blend"])
    for name in recipe["roles"]:
        if name not in rig.names:
            raise ValueError(f"Saved source bone is missing: {name}")
    if recipe.get("source_drop"):
        rig = variants.drop(rig, recipe["source_drop"])
        bpy.ops.wm.save_as_mainfile(filepath=rig.blend)
    if recipe.get("source_edit"):
        if recipe["source_edit"] not in ("swampert_straighten", "plusle_rebind"):
            raise ValueError("Unknown source preparation recipe")
        import runpy
        dest = load_dir / "skeleton-fit.blend"
        previous = sys.argv
        script = Path(__file__).parent / "cast" / (recipe["source_edit"] + ".py")
        try:
            sys.argv = [str(script), rig.blend, str(dest)]
            runpy.run_path(str(script), run_name="__main__")
        finally:
            sys.argv = previous
        rig = rigs.read(dest)
    body.FIX = recipe.get("body_fix", {})
    if recipe.get("drop"):
        rig = variants.drop(rig, recipe["drop"])
    named = {}
    children = rig.children()
    for chain in recipe.get("chains", []):
        if not chain["kind"]:
            continue
        bones = [rig.names.index(n) for n in chain["roots"]]
        for b in bones:
            bones += children[b]
        for b in bones:
            named[rig.names[b]] = {k: chain[k] for k in ("kind", "held_out")}
    fighter = recipe["fighter"]
    slots = read_weapons(targets / f"{fighter}.glb")
    frig, farm, fmeshes = rigs.import_fighter(targets / f"{fighter}.glb")
    description = correspond.read_description(targets / f"{fighter}.description.json")
    upright = repose.normalize(rig, np.array(recipe["up"]), np.array(recipe["front"]), 1.0)
    canonical = (np.array([0., 0., 1.]), np.array([0., -1., 0.]))
    roles, forks = recipe["roles"], recipe["forks"]
    shape = body.read(rig, *canonical, roles, forks)
    k = size_to_target(rig, shape, frig, description, rigs.objects(rig), fmeshes)
    scaled = repose.normalize(rig, *canonical, k)
    to_rest = scaled[:3, :3] @ upright[:3, :3]
    shape = body.read(rig, *canonical, roles, forks)
    match = correspond.match(rig, shape, frig, description, items=item_joints(fighter), slots=slots,
                             named=named, kinds=recipe.get("equipment", {}), digits=set(recipe.get("digits", [])))
    gown = cloth.gown(rig, match, frig, description)
    bones = sorted(match.embedded)
    w = cloth.weights(rig, match.owner, bones, gown) if gown else repose.fighter_weights(rig, match.owner, bones)
    w = repose.alone(w, bones, match.whole)
    w = repose.split(rig, w, bones, match.splits, match.owner)
    surface = repose.Surface(rig)
    w, _ = surface.blend(w, bones, match.embedded)
    if gown and gown.held is not None:
        held_by, held, moves = cloth.rest(rig, match.owner, bones, gown, {})
        held = repose.split(rig, repose.alone(held, held_by, match.whole), held_by, match.splits, match.owner)
        embedded = {**match.embedded, **{("held", fb): match.embedded[fb] for fb in gown.columns}}
        held, _ = surface.blend(held, held_by, embedded)
    else:
        held_by, held, moves = bones, w, {}
    transforms = repose.transforms(match, bones)
    moves = {**transforms, **moves}
    points = repose.deform(rig.points, held, held_by, moves)
    if recipe.get("save_mapping"):
        import numpy as np
        np.savez_compressed(out / "ends.npz", source=rig.points, placed=points, weights=w,
                            bones=np.asarray([frig.names[b] for b in bones]))
    chains, carried = build.loose(rig, match, transforms, frig, w, bones)
    build_dir = out / "3-build"
    build.write(build_dir, rig, points, w, bones, frig, farm, fmeshes, fighter, chains, carried,
                jacobians=repose.jacobians(rig.points, held, held_by, moves) @ to_rest)
    for name in recipe.get("opaque", []):
        image = bpy.data.images[name]
        pixels = paint._pixels(image)
        pixels[..., 3] = 255
        paint._packed(image, "-opaque", pixels)
    if recipe.get("opaque"):
        # A character with no separate eye surface skips the eye writer, so
        # persist its reviewed material changes before hang reopens the build.
        bpy.ops.wm.save_as_mainfile(filepath=str(build_dir / "build.blend"))
    eye_record = replay_eyes(build_dir, head_weights(rig, shape), recipe["eyes"], load_dir / "source")
    hanging = hang.settle(build_dir)
    if match.replaced:
        (build_dir / "weapons_replaced.json").write_text(json.dumps(match.replaced, indent=2), encoding="utf-8")
    record = {"fighter": fighter, "scale": float(k), "eyes": eye_record, "hang": hanging,
              "owners": {rig.names[mb]: frig.names[fb] for mb, fb in match.owner.items()},
              "network": "disabled", "authoring": "disabled"}
    (out / "replay.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


if __name__ == "__main__":
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    record = replay(json.loads(Path(job["recipe"]).read_text(encoding="utf-8")), Path(job["model"]),
                    Path(job["targets"]), Path(job["out"]))
    print("Replayed", record["fighter"], "from fixed choices", flush=True)
