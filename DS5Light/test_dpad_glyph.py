"""Directional icons must use single-direction sprite cells."""
import tkinter as tk
import unittest
from controller_glyphs import CROPS, readable, glyph


class DpadGlyphTests(unittest.TestCase):
    def test_single_direction_cells_and_rendering(self):
        root=tk.Tk();root.withdraw()
        try:
            for arrow,cell in zip(('↑','↓','←','→'),((0,462),(42,462),(84,462),(126,462))):
                self.assertEqual(CROPS[readable(arrow)],cell)
                icon=glyph(root,arrow)
                self.assertIsNotNone(icon)
                self.assertGreater(icon.width(),0)
            up,down=glyph(root,'↑'),glyph(root,'↓')
            self.assertNotEqual(root.tk.call(str(up),'data'),root.tk.call(str(down),'data'))
        finally:root.destroy()


if __name__=='__main__':unittest.main()
