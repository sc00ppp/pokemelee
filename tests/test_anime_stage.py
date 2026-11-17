"""What AniMelee's stage outline takes for a line."""
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


if __name__ == "__main__":
    unittest.main()
