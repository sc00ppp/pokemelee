"""hand_magmar_feet.py <build dir> Mario: stand_feet.py for Magmar, with its feet turned to face forward first.

Owner 2026-11-12: "seems like magmars feet are backwards". Colosseum's Magmar has its white claws at the front of each foot;
rigswap's port (pokecast-4/colomagmar-Mario, before any hand step) has them at the back. So after stand_feet hands the foot
its weight (give_foot) and before it stands the foot, each foot turns half a circle about the vertical line through its
ankle, every point by its share on the foot's joints (the ankle ring, near that line, hardly moves). stand_feet then lays
the sole, slides it to the vanilla depth and puts the front part on the toe joint by position, as for every port.

round_cast.sh runs this in place of stand_feet.py for hand/magmar-Mario/round. No AI asks."""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
source = (HERE / 'stand_feet.py').read_text(encoding='utf-8')
source = source[:source.rindex('\nmain()')]                 # its functions, without its run
exec(compile(source, 'stand_feet.py', 'exec'))


def face_forward(side, names, rest, below):
    """the foot turned 180 degrees about the vertical through its ankle, each point by its share on the foot"""
    joints = below[names[f'{side}FootJ']]
    ankle = rest[names[f'{side}FootJ']][:3, 3]
    before = foot_points(joints)
    for ob in meshes():
        pts, held = game_points(ob), weights(ob)
        share = np.array([sum(w for k, w in h.items() if k in joints) / (sum(h.values()) or 1) for h in held])
        moved = share > 0
        axis = np.array([ankle[0], 0, ankle[2]])
        spin = np.outer(share[moved] * np.pi, [0, 1, 0])
        pts[moved] = axis + turned(pts[moved] - axis, spin)
        mw = np.array(ob.matrix_world)
        ob.data.vertices.foreach_set('co', ((pts @ C.T - mw[:3, 3]) @ np.linalg.inv(mw[:3, :3]).T).ravel())
        ob.data.update()
    after = foot_points(joints)
    print('%s foot turned to face forward: %d points, front-back extent from the ankle %.2f..%.2f -> %.2f..%.2f' % (
        side, len(before), (before[:, 2] - ankle[2]).min(), (before[:, 2] - ankle[2]).max(),
        (after[:, 2] - ankle[2]).min(), (after[:, 2] - ankle[2]).max()))


def main():
    build, fighter = Path(sys.argv[1]), sys.argv[2]
    read = sole
    names = {v: k for k, v in JOINT_NAMES[fighter].items()}
    rest, below = skeleton(fighter)
    own = vanilla_feet(fighter, rest, below, names, read)
    bpy.ops.wm.open_mainfile(filepath=str(build / 'edited.blend'))
    feet = {}
    for side in 'LR':
        print(fighter, side, 'foot took over', give_foot(side, names, rest, below), 'points')
        face_forward(side, names, rest, below)
        feet[side] = foot_points(below[names[f'{side}FootJ']])
        if len(feet[side]) < 4:
            print(fighter, side, 'has no foot to stand')
            del feet[side]
    if feet:
        turn = tips(feet, own, read)
        for side in feet:
            stand(side, fighter, own[side], turn[side], names, rest, below)
            bend_toe(side, own[side], names, below)
    bpy.ops.wm.save_as_mainfile(filepath=str(build / 'edited.blend'))


main()
