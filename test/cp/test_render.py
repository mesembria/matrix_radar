import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "..", "circuitpython"))
sys.path.insert(0, HERE)
import radar  # noqa: E402
from radar import Radar  # noqa: E402
from fakes import FakeBitmap  # noqa: E402
import scenario  # noqa: E402

RADAR_DATA = (" UA1482,DEN>SFO,B738,-52,31,270,280,18500;N172SP,,C172,40,-20,315,100,1400;"
              "N815SR,,SR22,-60,-50,45,150,4500;F91307,DEN>MSP,A21N,80,70,30,300,25000")
DETAILS_DATA = ("UA1482,DEN>SFO,B738,-52,31,270,280,18500;N172SP,,C172,10,-5,315,100,1400;"
                "N4417K,,PA28,-8,6,120,95,2200;F91307,DEN>MSP,A21N,80,70,30,300,25000")


# The C++ reference colors, so frames compare by layout whatever the palette is.
REFERENCE_COLORS = [
    (0, 0, 0), (255, 110, 0), (70, 210, 40), (40, 100, 255), (80, 32, 0), (16, 60, 10),
    (10, 26, 80), (230, 230, 225), (170, 165, 150), (110, 108, 100), (40, 40, 38),
    (0, 70, 50), (0, 28, 20), (35, 35, 35),
]


EAST = "E,,,50,0,90,0,1500"


def frame(r, now):
    r.range_mi, r.ring_mi = 10, 2
    r.update(now)
    bmp = FakeBitmap()
    r.draw(bmp, now)
    return bmp


class Snapshot(unittest.TestCase):
    def test_frames_match_snapshot(self):
        with open(scenario.GOLDEN) as f:
            want = f.read()
        got = scenario.render_text()
        if got != want:
            w, g = want.splitlines(), got.splitlines()
            diff = [(i, a, b) for i, (a, b) in enumerate(zip(w, g)) if a != b][:10]
            self.fail("screens changed; if on purpose, run make_golden.py\n" +
                      "\n".join("%4d want %s\n     got  %s" % d for d in diff))


class SweepAndPalette(unittest.TestCase):
    def test_sweep_off(self):
        off = Radar()
        off.parse(RADAR_DATA, 1000)
        off.set_sweep(False)
        b = frame(off, 2000)
        on = Radar()
        a = frame(on, 2000)
        sweep = (radar.SWEEP, radar.SWEEP_TAIL)
        self.assertFalse(any(c in sweep for row in b.px for c in row))
        self.assertTrue(any(c in sweep for row in a.px for c in row))

    def test_palette_size(self):
        self.assertEqual(len(radar.COLORS), 32)
        want = tuple(int(v * 0.5) for v in radar.COLORS[radar.HI_LOW])
        self.assertEqual(radar.COLORS[radar.faded(radar.HI_LOW, 2)], want)
        self.assertEqual(radar.faded(radar.LO_HIGH, 0), radar.LO_HIGH)

    def test_radar_draws_painted_position(self):
        r = Radar()
        r.parse(EAST, 0)
        for t in range(0, 5300, 100):
            r.update(t)
        b = frame(r, 5300)
        self.assertEqual(b[22, 16], radar.HI_LOW)  # revealed at 5 mi east
        r.parse("E,,,50,30,90,0,1500", 5400)  # moved north
        for t in range(5400, 12000, 100):
            r.update(t)
        b = frame(r, 12000)
        self.assertEqual(b[22, 12], 0)  # new spot not shown until the sweep passes
        self.assertEqual(b[22, 16], radar.faded(radar.HI_LOW, r.fade_level("E", 12000)))
        self.assertGreater(r.fade_level("E", 12000), 0)

    def test_unrevealed_not_drawn(self):
        r = Radar()
        r.parse(EAST, 0)
        b = frame(r, 1000)
        self.assertEqual(b[22, 16], 0)
        self.assertEqual(b[51, 22], radar.HI_LOW)  # the count "1" for low planes stays live

    def test_sweep_off_draws_live(self):
        r = Radar()
        r.parse(EAST, 0)
        r.set_sweep(False)
        b = frame(r, 1000)
        self.assertEqual(b[22, 16], radar.HI_LOW)

    def test_green_radar_colored_planes(self):
        # Philippe's choice: radar, sweep and text in green; planes keep their band colors.
        for i in (radar.WHITE, radar.SOFT, radar.GRAY, radar.DIM,
                  radar.SWEEP, radar.SWEEP_TAIL, radar.BAR_OFF):
            r, g, b = radar.COLORS[i]
            self.assertTrue(g > r and g > b, (i, radar.COLORS[i]))
        self.assertEqual(radar.COLORS[1:7], REFERENCE_COLORS[1:7])
        # Text stays brighter than the rings, rings brighter than the faint outer circle.
        g = [radar.COLORS[i][1] for i in (radar.WHITE, radar.SOFT, radar.GRAY, radar.DIM)]
        self.assertEqual(g, sorted(g, reverse=True))

    def test_palette(self):
        full = radar.palette_colors(255)
        self.assertEqual(full[0], 0)
        self.assertEqual(full[radar.HI_LOW], 0xFF6E00)
        low = radar.palette_colors(5)
        for i, (r, g, b) in enumerate(radar.COLORS):
            c = low[i]
            for want, got in ((r, c >> 16), (g, (c >> 8) & 0xFF), (b, c & 0xFF)):
                if want:
                    self.assertGreaterEqual(got, 1, i)
                else:
                    self.assertEqual(got, 0, i)


if __name__ == "__main__":
    unittest.main()
