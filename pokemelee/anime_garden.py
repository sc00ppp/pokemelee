"""Accepted garden treatment: silhouettes, without internal lines on its Pokemon."""
import numpy as np
from . import anime_stage

def meshes(path):
    """[(place joint, world points)] of every mesh, as anime.py's model_points reads them"""
    d = anime_stage.Dat.read(path)
    worlds = anime_stage.world_matrices(d)
    out = []
    for j, o in anime_stage.places(d, worlds):
        for p in d.chain(d.ptr(o + 12), 4):
            table = anime_stage.attrs(d, p)
            pos = next((a for a in table if a['name'] == anime_stage.POS), None)
            if pos is None or pos['data'] is None:
                continue
            space = anime_stage.skinned_matrix(d, p, worlds) if d.u16(p + 12) & anime_stage.ENVELOPE else worlds[d.ptr(p + 20) or j]
            pts = np.array([space[:3, :3] @ np.array(anime_stage.read_vector(d, pos, index[anime_stage.POS])) + space[:3, 3]
                            for _, rows in anime_stage.strips(d, p, table) for _, index in rows])
            if len(pts):
                out.append((j, pts))
    return out


def near(pts, at, r):
    return bool((np.abs(pts[:, 0] - at[0]) < r).all() and (np.abs(pts[:, 2] - at[2]) < r).all())


def edge_filter(path, spec):
    spots = [x["place"]["t"] for x in spec["donors"] if any(k in x["file"] for k in ("pikachu", "maril", "guraena"))]
    all_meshes = meshes(path)
    pika = min(j for j, pts in all_meshes if near(pts, spots[0], 14))
    birds = max(j for j, pts in all_meshes if near(pts, (0, 0, 0), 8) and np.ptp(pts, 0).max() < 10)
    mon = [(j, pts) for j, pts in all_meshes if pika <= j <= birds]
    for j, pts in mon:
        if not (any(near(pts, at, 32) for at in spots) or near(pts, (0, 0, 0), 8)):
            raise ValueError(f'joint {j} in the mon range is not a mon: {pts.min(0)} .. {pts.max(0)}')
    own = {tuple(np.round(q, 2)) for _, pts in mon for q in pts}
    return lambda a, b, sides: not (tuple(np.round(a, 2)) in own and tuple(np.round(b, 2)) in own) and anime_stage.seen(a, b, sides)
