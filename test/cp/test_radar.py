import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "circuitpython"))
import radar  # noqa: E402
from radar import Radar, TICKS_PERIOD  # noqa: E402

DETAILS_DATA = ("UA1482,DEN>SFO,B738,-52,31,270,280,18500;N172SP,,C172,10,-5,315,100,1400;"
                "N4417K,,PA28,-8,6,120,95,2200;F91307,DEN>MSP,A21N,80,70,30,300,25000")


def in_details(now=3000):
    r = Radar()
    r.parse(DETAILS_DATA, 2000)
    r.update(now)
    return r


class ParseTest(unittest.TestCase):
    def test_parse_basic(self):
        r = Radar()
        r.parse(" UA1482,DEN>SFO,B738,-52,31,270,280,18500;N172SP,,C172,40,-20,315,100,1400", 0)
        self.assertEqual(len(r.planes), 2)
        p = r.planes[0]
        self.assertEqual((p.id, p.route, p.type), ("UA1482", "DEN>SFO", "B738"))
        self.assertAlmostEqual(p.x0, -5.2)
        self.assertAlmostEqual(p.y0, 3.1)
        self.assertEqual((p.hdg, p.spd, p.agl), (270, 280, 18500))
        self.assertEqual(r.planes[1].route, "")

    def test_parse_skips_bad_records(self):
        r = Radar()
        r.parse("A,,,1,2,3,4,5;SHORT,1,2;B,,,x,2,3,4,5;C,,,1,2,3,4,-50", 0)
        self.assertEqual([p.id for p in r.planes], ["A", "C"])
        self.assertEqual(r.planes[1].agl, 0)

    def test_parse_empty_is_data(self):
        r = Radar()
        r.parse("", 0)
        self.assertEqual(r.planes, [])
        self.assertTrue(r.have_data)
        r.update(1000)
        self.assertFalse(r.stale(1000))


class MotionTest(unittest.TestCase):
    def test_coast(self):
        r = Radar()
        r.parse("P,,,0,0,90,100,5000", 0)
        r.update(36_000)
        self.assertAlmostEqual(r.planes[0].x, 1.15078, delta=0.001)
        r.update(120_000)
        self.assertAlmostEqual(r.planes[0].x, 1.918, delta=0.001)

    def test_stale_clears(self):
        r = Radar()
        r.parse("P,,,0,0,90,100,5000", 0)
        r.update(120_001)
        self.assertEqual(r.planes, [])
        self.assertTrue(r.stale(120_001))

    def test_tick_wrap(self):
        r = Radar()
        r.parse("P,,,0,0,90,100,5000", TICKS_PERIOD - 1000)
        r.update(500)
        self.assertFalse(r.stale(500))
        self.assertAlmostEqual(r.planes[0].x, 100 * 1.15078 / 3600 * 1.5, delta=0.0001)


class RingTest(unittest.TestCase):
    def test_ring_order_and_rotate(self):
        r = in_details()
        self.assertEqual(r.ring, ["N4417K", "N172SP"])  # closest first
        self.assertTrue(r.details_now)
        self.assertEqual(r.idx, 0)
        r.update(9500)
        self.assertEqual(r.idx, 1)

    def test_tap_details_pauses(self):
        r = in_details()
        r.update(9500)
        self.assertIsNone(r.tap(-1, 9600))
        self.assertEqual(r.idx, 0)
        r.parse(DETAILS_DATA, 38_000)  # fresh data keeps both planes in the ring
        r.update(38_600)
        self.assertEqual(r.idx, 0)  # paused
        r.update(39_700)
        self.assertEqual(r.idx, 0)  # pause over, fresh 6 s starts
        r.update(45_800)
        self.assertEqual(r.idx, 1)

    def test_hold_details_quiet(self):
        r = in_details()
        self.assertIsNone(r.hold(1, 3100))
        self.assertEqual(r.toast(3100), ("RADAR", "2 MIN"))
        r.parse(DETAILS_DATA, 60_000)
        r.update(63_100)
        self.assertFalse(r.details_now)
        r.parse(DETAILS_DATA, 122_000)
        r.update(123_200)
        self.assertTrue(r.details_now)


class SettingsTest(unittest.TestCase):
    def test_tap_radar_range(self):
        r = Radar()
        self.assertEqual(r.tap(1, 0), {"range": 20})
        self.assertEqual(r.toast(0), ("RANGE", "20 MI"))
        self.assertEqual(r.tap(1, 10), {"range": 20})
        r.set_range(15)
        self.assertEqual(r.tap(-1, 20), {"range": 10})
        self.assertIsNone(r.toast(20 + radar.TOAST_MS))

    def test_hold_radar_ring(self):
        r = Radar()
        self.assertEqual(r.hold(-1, 0), {"ring": 1})
        self.assertEqual(r.toast(0), ("RING", "1 MI"))
        r.set_ring(1.5)
        self.assertEqual(r.hold(1, 10), {"ring": 2})
        self.assertEqual(radar.fmt_mi(1.5), "1.5 MI")
        self.assertEqual(radar.fmt_mi(10), "10 MI")

    def test_toggle_sweep(self):
        r = Radar()
        self.assertTrue(r.sweep_on)
        self.assertEqual(r.toggle_sweep(0), {"sweep": False})
        self.assertEqual(r.toast(0), ("SWEEP", "OFF"))
        self.assertEqual(r.toggle_sweep(10), {"sweep": True})

    def test_snap(self):
        self.assertEqual(radar.snap_range(7), 5)
        self.assertEqual(radar.snap_range(999), 20)
        self.assertEqual(radar.snap_range(15), 15)
        self.assertEqual(radar.snap_ring(0.1), 0.5)
        self.assertEqual(radar.snap_ring(1.3), 1.5)
        self.assertEqual(radar.snap_ring(9), 3)

    def test_elapsed_wraps(self):
        self.assertEqual(radar.elapsed(5, TICKS_PERIOD - 5), 10)


if __name__ == "__main__":
    unittest.main()
