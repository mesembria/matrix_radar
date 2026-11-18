import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "circuitpython"))
from buttons import Buttons  # noqa: E402
from radar import TICKS_PERIOD  # noqa: E402


def run(up, down, start=0, end=7000):
    """Feed samples every 10 ms. up/down: t -> pressed. Returns [(t, event)]."""
    b = Buttons()
    out = []
    for t in range(start, end, 10):
        ev = b.update(up(t - start), down(t - start), t % TICKS_PERIOD)
        if ev:
            out.append((t - start, ev))
    return out


def held(a, z):
    return lambda t: a <= t < z


never = held(0, 0)


class ButtonsTest(unittest.TestCase):
    def test_tap_up(self):
        out = run(held(0, 200), never)
        self.assertEqual([e for _, e in out], [("tap", 1)])
        self.assertTrue(200 <= out[0][0] <= 230)

    def test_hold_down(self):
        self.assertEqual([e for _, e in run(never, held(0, 1000))], [("hold", -1)])

    def test_gap_length_ignored(self):
        self.assertEqual(run(held(0, 650), never), [])

    def test_too_long(self):
        self.assertEqual(run(held(0, 6000), never), [])

    def test_bounce(self):
        self.assertEqual(run(held(100, 110), never), [])

    def test_both_release_order(self):
        out = run(held(0, 300), held(0, 450))
        self.assertEqual([e for _, e in out], [("both",)])
        self.assertTrue(450 <= out[0][0] <= 480)

    def test_both_short_overlap(self):
        out = run(held(0, 200), held(150, 200))
        self.assertEqual(sorted(e for _, e in out), [("tap", -1), ("tap", 1)])

    def test_wrap(self):
        out = run(held(0, 200), never, start=TICKS_PERIOD - 100, end=TICKS_PERIOD + 400)
        self.assertEqual([e for _, e in out], [("tap", 1)])


if __name__ == "__main__":
    unittest.main()
