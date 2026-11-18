import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "circuitpython"))
import radar  # noqa: E402
from radar import Radar  # noqa: E402

EAST = "E,,,50,0,90,0,1500"  # due east, 5 mi, not moving


def run(r, start, end, step=100):
    for t in range(start, end, step):
        r.update(t)


class SweepTest(unittest.TestCase):
    def test_period(self):
        self.assertEqual(radar.sweep_period(5), 10000)
        for rng in (10, 15, 20):
            self.assertEqual(radar.sweep_period(rng), 20000)

    def test_hidden_until_swept(self):
        r = Radar()
        r.parse(EAST, 0)
        first = None
        for t in range(0, 8000, 100):
            r.update(t)
            if r.fade_level("E", t) is not None and first is None:
                first = t
                self.assertEqual(r.fade_level("E", t), 0)
        self.assertIn(first, (5000, 5100))

    def test_moves_only_on_pass(self):
        r = Radar()
        r.parse("M,,,0,-50,90,360,1500", 0)
        run(r, 0, 12000)
        x1 = r.painted["M"][0]
        run(r, 12000, 15000)
        self.assertEqual(r.painted["M"][0], x1)
        run(r, 15000, 40000)
        self.assertGreater(r.painted["M"][0], x1 + 1)

    def test_fade_steps(self):
        r = Radar()
        r.parse(EAST, 0)
        run(r, 0, 5200)
        shown = r.painted["E"][2]
        for dt, level in ((1000, 0), (5500, 1), (10500, 2), (15500, 3)):
            self.assertEqual(r.fade_level("E", shown + dt), level, dt)

    def test_wrap_north(self):
        r = Radar()
        r.parse("N,,,0,50,0,0,1500", 0)
        reveals = 0
        for t in range(0, 60001, 100):
            if t % 20000 == 0:
                r.parse("N,,,0,50,0,0,1500", t)  # keep the data fresh
            r.update(t)
            if "N" in r.painted and r.painted["N"][2] == t:
                reveals += 1
        self.assertEqual(reveals, 3)

    def test_long_gap(self):
        r = Radar()
        r.parse(EAST + ";W,,,-50,0,0,0,1500;S,,,0,-50,0,0,1500", 0)
        r.update(0)
        r.update(25000)
        self.assertEqual({k: v[2] for k, v in r.painted.items()}, {"E": 25000, "W": 25000, "S": 25000})

    def test_zoom_mid_turn(self):
        r = Radar()
        run(r, 0, 5001)
        self.assertAlmostEqual(r.sweep_deg, 90, delta=0.01)
        r.set_range(5)
        r.update(5100)
        self.assertAlmostEqual(r.sweep_deg, 93.6, delta=0.01)

    def test_leave_and_return(self):
        r = Radar()
        r.parse(EAST, 0)
        run(r, 0, 5200)
        self.assertIn("E", r.painted)
        r.parse("E,,,150,0,90,0,1500", 6000)
        r.update(6000)
        self.assertNotIn("E", r.painted)
        r.parse(EAST, 7000)
        r.update(7000)
        self.assertIsNone(r.fade_level("E", 7000))

    def test_plane_moving_against_sweep(self):
        # Found in the scenario: a plane whose bearing shrinks can slip back past
        # the sweep line between two frames. It must still be revealed.
        r = Radar()
        r.parse("F,,,10,-2,0,2000,1500", 0)  # 1 mi east, racing north: bearing drops fast
        seen = False
        for t in range(0, 15000, 100):  # it leaves the 10 mi range after ~15 s
            r.update(t)
            seen = seen or "F" in r.painted
        self.assertTrue(seen)

    def test_sweep_off_clears(self):
        r = Radar()
        r.parse(EAST, 0)
        run(r, 0, 5200)
        r.set_sweep(False)
        r.update(5300)
        self.assertEqual(r.painted, {})


if __name__ == "__main__":
    unittest.main()
