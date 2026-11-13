"""Directional icons must use single-direction sprite cells."""
import tkinter as tk
import unittest
from controller_glyphs import CROPS, readable, glyph


class DpadGlyphTests(unittest.TestCase):
    def test_swipe_icon_uses_touch_area_not_swipe_direction(self):
        root=tk.Tk();root.withdraw()
        try:
            for area,english,button in (('왼쪽','left','터치패드 왼쪽 클릭'),('오른쪽','right','터치패드 오른쪽 클릭'),('전체','anywhere','터치패드 클릭')):
                expected=glyph(root,button)
                for fingers in (1,2):
                    for direction,english_direction in (('위','up'),('아래','down'),('왼쪽','left'),('오른쪽','right')):
                        for caption in (f'터치 {area} · {fingers}손가락 · {direction}',f'Touch {english} · {fingers} fingers · {english_direction}',f'Touch {english}, {fingers} finger, {english_direction}'):
                            with self.subTest(caption=caption):self.assertIs(glyph(root,caption),expected)
        finally:root.destroy()
    def test_touch_icons_have_full_left_right_translucent_gold(self):
        root=tk.Tk();root.withdraw()
        try:
            icons=[glyph(root,value,32) for value in ('터치패드 클릭','터치패드 왼쪽 클릭','터치패드 오른쪽 클릭')]
            for icon in icons:self.assertIsNotNone(icon)
            full,left,right=icons
            # Sample away from the border, centre divider and dot texture.
            self.assertFalse(full.transparency_get(8,12))
            self.assertFalse(full.transparency_get(23,12))
            self.assertFalse(left.transparency_get(8,12))
            self.assertTrue(left.transparency_get(23,12))
            self.assertTrue(right.transparency_get(8,12))
            self.assertFalse(right.transparency_get(23,12))
            background=tk.PhotoImage(master=root,width=32,height=32)
            background.put('#151515',to=(0,0,32,32))
            root.tk.call(str(background),'copy',str(full),'-compositingrule','overlay')
            self.assertTrue(all(21<actual<gold for actual,gold in zip(background.get(8,12),(214,173,82))))
            self.assertIs(glyph(root,'터치 왼쪽',32),left)
            self.assertIs(glyph(root,'Left touchpad click',32),left)
            self.assertIs(glyph(root,'Right touchpad click',32),right)
        finally:root.destroy()
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
