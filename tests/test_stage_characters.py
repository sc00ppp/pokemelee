"""A stage's background characters, on a synthetic stage: one skinned triangle and one rigid one."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

import numpy as np

from pokemelee import stage_characters
from pokemelee.dat import Dat
from pokemelee.display_list import CLR0, END, ENVELOPE, NRM, POS, attrs, strips

TRIANGLES, DIRECT, INDEX8, FLOAT = 0x90, 1, 2, 4
LIT, UNLIT = 0x2015, 0x2011        # constant colour and a texture, with and without the lights


def stage(bone_turn=(0., 0., 0.), skeleton_root=False, one_sided=True):
    """map_head -> one group -> root -> a skinned branch (lit, facing the camera) and a rigid one (unlit)."""
    names = b"map_head\0"
    head = bytes(0x10)
    raw = struct.pack(">5I", 0x20 + len(head) + 8 + len(names), len(head), 0, 1, 0) + bytes(12) + head + struct.pack(">2I", 0, 0) + names
    d = Dat(raw)

    def joint(child=None, sibling=None, dobj=None, move=(0, 0, 0), turn=(0, 0, 0), flags=0x80):
        at = d.add(struct.pack(">2I", 0, flags) + bytes(12) + struct.pack(">9f", *turn, 1, 1, 1, *move) + bytes(8))
        for field, target in ((8, child), (0xc, sibling), (0x10, dobj)):
            if target is not None:
                d.point(at + field, target)
        return at

    def mesh(mode, skin_to=None, x=0.):
        points = d.add(struct.pack(">9f", x, 0, 0, x + 1, 0, 0, x, 1, 0), 32)
        normals = d.add(struct.pack(">6f", 0, 0, 1, 0, 1, 0), 32)       # towards the camera, and straight up
        rows = [(0, DIRECT, 0, 0, 0, None)] if skin_to is not None else []
        rows += [(POS, INDEX8, 1, FLOAT, 12, points), (NRM, INDEX8, 0, FLOAT, 12, normals)]
        table = d.add(b"".join(struct.pack(">4IBBHI", name, kind, count, comp, 0, 0, stride, 0)
                               for name, kind, count, comp, stride, _ in rows) + struct.pack(">I", END) + bytes(20), 32)
        for i, row in enumerate(rows):
            if row[5] is not None:
                d.point(table + i * 24 + 20, row[5])
        vertex = (lambda i, n: bytes((0, i, n))) if skin_to is not None else (lambda i, n: bytes((i, n)))
        listing = struct.pack(">BH", TRIANGLES, 3) + vertex(0, 0) + vertex(1, 0) + vertex(2, 1)
        pobj = d.add(struct.pack(">3I2H2I", 0, 0, 0, (ENVELOPE | (0x8000 if one_sided else 0)) if skin_to is not None else 0, 1, 0, 0))
        d.point(pobj + 8, table)
        d.point(pobj + 16, d.add(listing + bytes(32 - len(listing)), 32))
        if skin_to is not None:
            envelope = d.add(struct.pack(">If2I", 0, 1., 0, 0))
            d.point(envelope, skin_to)
            array = d.add(bytes(8))
            d.point(array, envelope)
            d.point(pobj + 20, array)
        material = d.add(struct.pack(">12B2f", *(128, 128, 128, 255), *(255, 255, 255, 255), *(0, 0, 0, 255), 1., 1.))
        mobj = d.add(struct.pack(">6I", 0, mode, 0, 0, 0, 0))
        d.point(mobj + 12, material)
        dobj = d.add(bytes(16))
        d.point(dobj + 8, mobj)
        d.point(dobj + 12, pobj)
        return dobj, pobj, mobj

    bone = joint(turn=bone_turn)
    skinned = mesh(LIT, skin_to=bone)
    rigid = mesh(UNLIT, x=50.)
    scenery = joint(dobj=rigid[0])
    person = joint(child=bone, sibling=scenery, flags=0x82 if skeleton_root else 0x80)
    d.point(person + 0x10, skinned[0])
    root = joint(child=person)
    group = d.add(bytes(0x34))
    d.point(group, root)
    d.point(8, group)
    struct.pack_into(">I", d.data, 12, 1)
    return d, person, skinned, rigid


class StageCharacterTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.source = Path(self.folder.name) / "in.dat"
        d, self.person, self.skinned, self.rigid = stage()
        d.save(self.source)

    def test_a_character_is_the_branch_with_a_skinned_mesh(self):
        cast = stage_characters.characters(Dat.read(self.source))
        self.assertEqual([joints[0] for joints in cast], [self.person])

    def test_light_bakes_shading_into_the_character_only(self):
        target = Path(self.folder.name) / "out.dat"
        done = stage_characters.light(self.source, target)
        self.assertEqual((done["characters"], done["meshes"], done["materials"]), (1, 1, 1))
        before, d = Dat.read(self.source), Dat.read(target)
        _, pobj, mobj = self.skinned
        self.assertEqual(d.u32(mobj + 4), UNLIT & ~0b11 | 0b10)                      # unlit, coloured by its points
        table = attrs(d, pobj)
        self.assertEqual([a["name"] for a in table], [0, POS, NRM, CLR0])
        (_, rows), = strips(d, pobj, table)
        self.assertEqual([index[POS] for _, index in rows], [0, 1, 2])
        colour = next(a for a in table if a["name"] == CLR0)
        levels = [d.data[colour["data"] + 3 * index[CLR0]] for _, index in rows]
        front, up = (round(255 * stage_characters.shade(np.array(n, float))) for n in ((0, 0, 1), (0, 1, 0)))
        self.assertEqual(levels, [front, front, up])
        self.assertLess(stage_characters.shade(np.array((0., -1., 0.))), stage_characters.shade(np.array((0., 1., 0.))))
        _, rigid, rigid_mobj = self.rigid
        self.assertEqual(d.u32(rigid_mobj + 4), UNLIT)
        self.assertEqual([a["name"] for a in attrs(d, rigid)], [POS, NRM])
        self.assertEqual(d.ptr(rigid + 16), before.ptr(rigid + 16))
        self.assertEqual(d.ptr(pobj + 16), before.ptr(pobj + 16))       # the new list took the old one's block

    def test_a_vertex_on_one_bone_is_lit_in_that_bones_space(self):
        d, _, (_, pobj, _), _ = stage(bone_turn=(np.pi / 2, 0., 0.), skeleton_root=True)      # the bone turns front to down
        source, target = Path(self.folder.name) / "turned.dat", Path(self.folder.name) / "turned-out.dat"
        d.save(source)
        stage_characters.light(source, target)
        d = Dat.read(target)
        table = attrs(d, pobj)
        (_, rows), = strips(d, pobj, table)
        colour = next(a for a in table if a["name"] == CLR0)
        levels = [d.data[colour["data"] + 3 * index[CLR0]] for _, index in rows]
        down, front = (round(255 * stage_characters.shade(np.array(n, float))) for n in ((0, -1, 0), (0, 0, 1)))
        self.assertEqual(levels, [down, down, front])

    def test_a_recipe_and_its_stage_must_agree_on_the_characters(self):
        with self.assertRaisesRegex(ValueError, "1 characters and its recipe places 0"):
            stage_characters.flight_depths(self.source, {"donors": []})
        donor = {"file": "bird.dat", "place": {"t": [0, 0, 0]}, "path": {"points": [[0, 0, -100], [0, 0, -300]]}}
        self.assertEqual(stage_characters.flight_depths(self.source, {"donors": [donor]}), {self.skinned[1]: -200.})

    def test_foliage_is_the_scenery_inside_a_recipes_box(self):
        self.assertIsNone(stage_characters.plain_filter(self.source, {}))
        plain = stage_characters.plain_filter(self.source, {"foliage": [[-1, -1, -1, 60, 2, 1]]})
        inside, outside = np.array(((50., 0., 0.), (51., 1., 0.))), np.array(((50., 0., 0.), (70., 1., 0.)))
        self.assertTrue(plain(self.rigid[1], inside))
        self.assertFalse(plain(self.rigid[1], outside))
        self.assertFalse(plain(self.skinned[1], inside))        # a character keeps its outline wherever it stands

    def test_a_two_sided_part_keeps_its_border(self):
        d, *_ = stage(one_sided=False)
        source = Path(self.folder.name) / "sheet.dat"
        d.save(source)
        edge = np.array((0., 0., 0.)), np.array((1., 0., 0.)), [np.array((0., 0., -1.))]       # whichever way it faces
        self.assertFalse(stage_characters.edge_filter(source)(*edge))      # a sheet this small is narrower than two of its lines
        with mock.patch.object(stage_characters, "WIDE", 1):
            self.assertTrue(stage_characters.edge_filter(source)(*edge))

    def test_distance_to_triangles(self):
        triangles = np.array((((0., 0., 0.), (2., 0., 0.), (0., 2., 0.)), ((5., 5., 5.), (5., 5., 5.), (6., 5., 5.))))      # one real, one empty
        points = np.array(((.5, .5, 3.), (-1., 0., 0.), (5.5, 5., 6.)))
        np.testing.assert_allclose(stage_characters.distance(points, triangles), (3., 1., 1.))

    def test_quiet_is_what_a_recipe_names(self):
        self.assertIsNone(stage_characters.quiet_filter(self.source, {}))
        spec = {"wrappers": [{"t": [0, 0, 0], "s": 1.0}], "quiet": {"wrappers": [0], "boxes": [[-1, -1, -1, 2, 2, 1]]}}
        with self.assertRaisesRegex(ValueError, "2 joints placed as its recipe's wrapper 0"):
            stage_characters.quiet_filter(self.source, spec)
        quiet = stage_characters.quiet_filter(self.source, {"quiet": {"boxes": [[49, -1, -1, 52, 2, 1]]}})
        self.assertTrue(quiet(self.rigid[1], np.array(((50., 0., 0.), (51., 1., 0.)))))
        self.assertFalse(quiet(self.rigid[1], np.array(((50., 0., 0.), (60., 1., 0.)))))
        by_name = stage_characters.quiet_filter(self.source, {"quiet": {"meshes": [[50, 0, 0, 60.4, 1, 0]]}})
        self.assertTrue(by_name(self.rigid[1], np.array(((50., 0., 0.), (60., 1., 0.)))))          # its own bounds, near enough
        self.assertFalse(by_name(self.rigid[1], np.array(((50., 0., 0.), (55., 1., 0.)))))         # a smaller mesh inside them
        plain = stage_characters.plain_filter(self.source, {"plain": {"meshes": [[50, 0, 0, 60, 1, 0]]}})
        self.assertTrue(plain(self.rigid[1], np.array(((50., 0., 0.), (60., 1., 0.)))))

    def test_a_stage_without_characters_is_left_alone(self):
        d = Dat.read(self.source)
        struct.pack_into(">H", d.data, self.skinned[1] + 12, 0)
        d.point(self.skinned[1] + 20, None)
        plain = Path(self.folder.name) / "plain.dat"
        d.save(plain)
        target = Path(self.folder.name) / "untouched.dat"
        self.assertIsNone(stage_characters.light(plain, target))
        self.assertFalse(target.exists())

    def test_no_line_inside_a_character(self):
        visible = stage_characters.edge_filter(self.source)
        towards = [np.array((0., 0., 1.))]
        own = np.array((0., 0., 0.)), np.array((1., 0., 0.))
        scenery = np.array((50., 0., 0.)), np.array((51., 0., 0.))
        self.assertFalse(visible(*own, towards))
        self.assertTrue(visible(*scenery, towards))
        self.assertTrue(visible(own[0], scenery[0], towards))


if __name__ == "__main__":
    unittest.main()
