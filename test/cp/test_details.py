import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "..", "circuitpython"))
sys.path.insert(0, HERE)
import radar  # noqa: E402
from radar import Radar  # noqa: E402
from fakes import FakeBitmap  # noqa: E402


def details(data, now=1000, n_updates=1):
    r = Radar()
    r.ring_mi = 2
    r.parse(data, 0)
    r.update(now)
    bmp = FakeBitmap()
    r.draw(bmp, now)
    assert r.details_now, "expected the details page"
    return r, bmp


def lit(bmp, xs, ys):
    return [(x, y) for y in ys for x in xs if bmp[x, y]]


class DetailsTest(unittest.TestCase):
    def test_parse_model(self):
        r = Radar()
        r.parse("A,,C172,1,1,0,0,500,CESSNA 172;B,,PA28,1,1,0,0,500", 0)
        self.assertEqual([p.model for p in r.planes], ["CESSNA 172", ""])

    def test_type_line(self):
        _, b = details("A,,C172,0,10,0,0,500,CESSNA 172")
        self.assertTrue(lit(b, range(1, 40), range(22, 27)))
        self.assertFalse(lit(b, range(40, 64), range(22, 27)))  # "CESSNA 172" is 39 px wide
        _, b2 = details("A,,C172,0,10,0,0,500,")
        self.assertTrue(lit(b2, range(1, 16), range(22, 27)))   # falls back to "C172"
        self.assertFalse(lit(b2, range(16, 64), range(22, 27)))

    def test_mini_radar(self):
        _, b = details("A,,C172,0,10,0,0,500")
        self.assertEqual(b[radar.MCX, radar.MCY], radar.WHITE)
        self.assertEqual(b[53, 6], radar.HI_LOW)
        self.assertEqual(b[radar.MCX + radar.MR, radar.MCY], radar.DIM)

    def test_arrow_tail_behind(self):
        _, b = details("A,,C172,0,10,90,0,500")  # heading east
        self.assertEqual(b[53, 6], radar.HI_LOW)
        self.assertEqual(b[52, 6], radar.LO_LOW)
        self.assertEqual(b[51, 6], radar.LO_LOW)
        self.assertEqual(b[54, 6], 0)

    def test_closeness_bar(self):
        _, b = details("A,,C172,0,5,0,0,500")  # 0.5 of 2 mi
        self.assertEqual([b[x, 30] for x in (0, 47)], [radar.HI_LOW] * 2)
        self.assertEqual([b[x, 30] for x in (48, 63)], [radar.BAR_OFF] * 2)
        r, b = details("A,,C172,0,5,0,0,500;B,,C172,0,6,0,0,500")
        r.tap(-1, 1000)
        r.update(1100)
        bmp = FakeBitmap()
        r.draw(bmp, 1100)
        self.assertEqual(bmp[0, 30], radar.GRAY)  # paused

    def test_left_text_fits(self):
        r, b = details("N12345678901,DEN>SFO,B738,0,5,0,300,18500;B,,C172,0,6,0,0,500")
        self.assertEqual(lit(b, range(42, 44), range(0, 21)), [])
        self.assertTrue(lit(b, range(31, 42), range(1, 6)))  # "1/2" ends at x 41
        self.assertEqual(lit(b, range(29, 31), range(1, 6)), [])  # gap before "1/2"

    def test_no_distance_line(self):
        _, b = details("A,,C172,0,10,0,0,500")
        rows = lit(b, range(0, 64), range(20, 30))
        self.assertTrue(all(22 <= y <= 26 and x <= 15 for x, y in rows), rows)


if __name__ == "__main__":
    unittest.main()
