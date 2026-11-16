import unittest

from pokemelee import icons
from pokemelee.catalog import load
from pokemelee.native import menu_icons as art


class IconRecipeTest(unittest.TestCase):
    def test_recipe_covers_every_tile_with_cast_mons(self):
        recipe = load("icons.json")
        self.assertEqual(set(recipe["tiles"]), set(icons.KINDS))
        self.assertEqual(set(icons.KINDS), {*art.CAST, *art.PAIRS})
        cast = load("cast.json")
        mons = {row["pokemon"].lower() for row in cast["fighters"] + cast["partners"]}
        for name, tile in recipe["tiles"].items():
            for part in tile["parts"]:
                self.assertIn(part["mon"], mons, name)
                cx, cy, height = part["box"]
                self.assertTrue(0 < cx < 100 and 0 < cy < 100 and 0 < height <= 100, name)
                x, y, w, h = part.get("to", (0, 0, 1, 1))
                self.assertTrue(w > 0 and h > 0, name)

    def test_cut_fills_the_tile(self):
        from PIL import Image
        render = Image.new("RGBA", (100, 140), (255, 0, 0, 255))
        tile = icons.cut([{"mon": "x", "box": [50, 50, 20]}], {"x": render})
        self.assertEqual(tile.size, icons.TILE)
        self.assertEqual(tile.getpixel((icons.TILE[0] // 2, icons.TILE[1] // 2)), (255, 0, 0, 255))


if __name__ == "__main__":
    unittest.main()
