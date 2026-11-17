"""What AniMelee's stage outline takes for a line."""
import collections
import unittest

import numpy as np

from pokemelee import anime_stage

FRONT, UP = np.array((0., 0., 1.)), np.array((0., 1., 0.))


def lean(degrees):
    """A face normal leaning that far from the front, upwards."""
    return np.array((0., np.sin(np.radians(degrees)), np.cos(np.radians(degrees))))


def face(normal, said=None):
    """One of an edge's faces as the outline keeps it; ``said`` are the model's own normals at the edge's two ends."""
    a, b = np.zeros(3), np.array((1., 0., 0.))
    return (normal, 0, a, 0, b, 0, *(said or (None, None)))


class CreaseTests(unittest.TestCase):
    def test_a_fold_is_a_line_where_the_model_says_nothing(self):
        self.assertTrue(anime_stage.crease([face(FRONT), face(lean(50))]))
        self.assertFalse(anime_stage.crease([face(FRONT), face(lean(20))]))

    def test_a_border_is_a_line(self):
        self.assertTrue(anime_stage.crease([face(FRONT, (FRONT, FRONT))]))

    def test_a_fold_shaded_smoothly_is_a_bump_not_an_edge(self):
        smooth = (lean(25), lean(25))
        self.assertFalse(anime_stage.crease([face(FRONT, smooth), face(lean(50), smooth)]))

    def test_split_normals_or_a_sharp_fold_make_an_edge_again(self):
        self.assertTrue(anime_stage.crease([face(FRONT, (FRONT, FRONT)), face(lean(50), (lean(50), lean(50)))]))
        self.assertFalse(anime_stage.crease([face(FRONT, (FRONT, FRONT)), face(lean(50), (lean(50), FRONT))]))     # split at one end only
        smooth = (lean(45), lean(45))
        self.assertTrue(anime_stage.crease([face(FRONT, smooth), face(lean(90), smooth)]))


class SeamTests(unittest.TestCase):
    def edges(self, *rows):
        return {(tuple(map(float, a)), tuple(map(float, b))): [(n, 0, np.array(a, float), 0, np.array(b, float), 0, None, None)]
                for a, b, n in rows}

    def test_open_edges_lying_along_each_other_are_one_surface(self):
        long, left, right = ((0, 0, 0), (10, 0, 0)), ((0, 0, 0), (4, 0, 0)), ((4, 0, 0), (10, 0, 0))
        found = anime_stage.seams(self.edges((*long, FRONT), (*left, FRONT), (*right, FRONT)))
        self.assertEqual(len(found), 3)

    def test_a_corner_or_a_part_covered_edge_stays_a_border(self):
        long, left = ((0, 0, 0), (10, 0, 0)), ((0, 0, 0), (4, 0, 0))
        self.assertEqual(anime_stage.seams(self.edges((*long, FRONT), (*long[::-1], UP))), set())      # two walls meeting
        found = anime_stage.seams(self.edges((*long, FRONT), (*left, FRONT)))
        self.assertEqual(found, {((0., 0., 0.), (4., 0., 0.))})                                        # the long one is still open past 4

    def test_an_edge_off_the_line_is_no_seam(self):
        self.assertEqual(anime_stage.seams(self.edges(((0, 0, 0), (10, 0, 0), FRONT), ((0, 1, 0), (10, 1, 0), FRONT))), set())


class SliverTests(unittest.TestCase):
    def test_an_edge_along_a_sliver_is_cut_where_its_short_sides_meet(self):
        a, middle, b = (0., 0., 0.), (4., 0., 0.), (10., 0., 0.)
        row = lambda n, start, end: (n, 0, np.array(start), 0, np.array(end), 0, None, None)
        edges = collections.defaultdict(list)
        edges[a, b].append(row(UP, a, b))               # a lid along the sliver's long side
        edges[a, middle].append(row(FRONT, a, middle))  # past the sliver's short sides: a wall, then more lid
        edges[middle, b].append(row(UP, middle, b))
        anime_stage.split(edges, {(a, b): (middle, np.array(middle), 0)})
        self.assertNotIn((a, b), edges)
        self.assertTrue(anime_stage.crease(edges[a, middle]))       # the lid folds down into the wall
        self.assertFalse(anime_stage.crease(edges[middle, b]))      # and lies flat with the rest of itself

    def test_an_edge_no_sliver_lies_along_is_left_alone(self):
        a, b = (0., 0., 0.), (10., 0., 0.)
        edges = collections.defaultdict(list, {(a, b): [face(UP)]})
        anime_stage.split(edges, {((0., 1., 0.), (10., 1., 0.)): ((4., 1., 0.), np.array((4., 1., 0.)), 0)})
        self.assertEqual(list(edges), [(a, b)])


class WaterTests(unittest.TestCase):
    POOL = [(np.array((0., -10., 0.)), np.array((10., 0., 10.)))]     # floor at -10, surface at 0

    def dry(self, a, b):
        return anime_stage.dry(np.array(a, float), np.array(b, float), self.POOL)

    def test_a_line_into_the_water_stops_at_its_surface(self):
        (start, end), = self.dry((5, 10, 5), (5, -10, 5))
        self.assertAlmostEqual(start, 0.)
        self.assertAlmostEqual(end, .5, 3)

    def test_a_line_under_the_water_goes_and_one_beside_it_stays(self):
        self.assertEqual(self.dry((1, -5, 1), (9, -5, 1)), [])
        self.assertEqual(self.dry((11, -5, 1), (19, -5, 1)), [(0., 1.)])

    def test_a_line_through_the_water_keeps_both_ends(self):
        (s1, e1), (s2, e2) = self.dry((-10, -5, 5), (20, -5, 5))
        self.assertAlmostEqual(s1, 0.)
        self.assertAlmostEqual(e1, 1 / 3, 3)
        self.assertAlmostEqual(s2, 2 / 3, 3)
        self.assertAlmostEqual(e2, 1.)

    def test_a_crumb_left_above_the_water_is_dropped(self):
        self.assertEqual(self.dry((5, -anime_stage.DRY / 2, 5), (5, -5, 5)), [])

    def test_a_line_on_a_face_of_the_box_is_dry(self):
        self.assertEqual(self.dry((0, -5, 1), (0, -5, 9)), [(0., 1.)])      # the edge the water spills over
        self.assertEqual(self.dry((1, 0, 1), (9, 0, 1)), [(0., 1.)])        # where a wall meets the surface
        self.assertEqual(self.dry((1, -5, .01), (9, -5, .01)), [])          # just inside it is under


class EyeTests(unittest.TestCase):
    def test_a_face_turned_from_the_camera_is_seen_from_an_eye_off_to_its_side(self):
        a, b, side = np.array((100., 0., 0.)), np.array((100., 0., -50.)), [np.array((1., 0., 0.))]
        self.assertFalse(anime_stage.seen(a, b, side))
        self.assertTrue(anime_stage.seen(a, b, side, [anime_stage.EYE * (0, 1, 1) + (150., 0., 0.)]))


if __name__ == "__main__":
    unittest.main()
