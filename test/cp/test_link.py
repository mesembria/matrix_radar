import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "circuitpython"))
import link  # noqa: E402
from link import Link, decode, encode, discovery_messages  # noqa: E402


class FakeClient:
    def __init__(self):
        self.pubs = []  # (topic, msg, retain)
        self.subs = set()
        self.connects = []
        self.fail_connect = False
        self.fail_loop = False
        self.on_message = None
        self.now = 0

    def connect(self):
        self.connects.append(self.now)
        if self.fail_connect:
            raise OSError("broker down")

    def loop(self, timeout):
        if self.fail_loop:
            raise OSError(116)

    def publish(self, topic, msg, retain=False):
        self.pubs.append((topic, msg, retain))

    def subscribe(self, topic):
        self.subs.add(topic)

    def unsubscribe(self, topic):
        self.subs.discard(topic)

    def disconnect(self):
        pass

    def deliver(self, topic, msg):
        self.on_message(self, topic, msg)

    def states(self):
        return [(t, m) for t, m, r in self.pubs if t.endswith("/state") and r]


def make(values=None):
    c = FakeClient()
    planes, settings = [], []
    vals = values or {"range": 10, "ring": 2, "brightness": 128, "sweep": True}
    lk = Link(lambda: c, planes.append, lambda n, v: settings.append((n, v)), vals)
    return lk, c, planes, settings


def poll(lk, c, now):
    c.now = now
    lk.poll(now)


class PureTest(unittest.TestCase):
    def test_discovery(self):
        msgs = discovery_messages()
        self.assertEqual(len(msgs), 4)
        cfg = {t: json.loads(m) for t, m in msgs}
        rng = cfg["homeassistant/number/flight_radar_range/config"]
        self.assertEqual((rng["min"], rng["max"], rng["step"]), (5, 20, 5))
        self.assertEqual(rng["unit_of_measurement"], "mi")
        self.assertEqual(rng["command_topic"], "flight_radar/range/set")
        self.assertEqual(rng["state_topic"], "flight_radar/range/state")
        ring = cfg["homeassistant/number/flight_radar_ring/config"]
        self.assertEqual((ring["min"], ring["max"], ring["step"]), (0.5, 3, 0.5))
        br = cfg["homeassistant/number/flight_radar_brightness/config"]
        self.assertEqual((br["min"], br["max"], br["step"]), (5, 255, 1))
        sw = cfg["homeassistant/switch/flight_radar_sweep/config"]
        self.assertEqual(sw["name"], "Sweep")
        for c in cfg.values():
            self.assertEqual(c["availability_topic"], "flight_radar/status")
            self.assertEqual(c["device"]["name"], "Flight Radar")

    def test_decode(self):
        self.assertEqual(decode("range", "7"), 5)
        self.assertIsNone(decode("range", "abc"))
        self.assertEqual(decode("brightness", "999"), 255)
        self.assertEqual(decode("brightness", "127.6"), 128)
        self.assertEqual(decode("ring", "0"), 0.5)
        self.assertIs(decode("sweep", "off"), False)
        self.assertIsNone(decode("sweep", "maybe"))
        self.assertIsNone(decode("range", "nan"))

    def test_encode(self):
        self.assertEqual(encode("range", 10), "10")
        self.assertEqual(encode("ring", 1.5), "1.5")
        self.assertEqual(encode("ring", 2.0), "2")
        self.assertEqual(encode("brightness", 128), "128")
        self.assertEqual(encode("sweep", True), "ON")

    def test_next_delay(self):
        self.assertEqual([link.next_delay(a) for a in (0, 1, 2, 10)], [2000, 4000, 8000, 60000])


class LinkTest(unittest.TestCase):
    def test_restore_then_publish(self):
        lk, c, _, settings = make()
        poll(lk, c, 0)
        self.assertTrue(lk.connected)
        self.assertIn("flight_radar/range/state", c.subs)
        self.assertIn(("flight_radar/status", "online", True), c.pubs)
        c.deliver("flight_radar/range/state", "20")
        self.assertEqual(settings, [("range", 20)])
        poll(lk, c, 2900)
        self.assertEqual(c.states(), [])
        poll(lk, c, 3000)
        self.assertEqual(sorted(c.states()), [
            ("flight_radar/brightness/state", "128"),
            ("flight_radar/range/state", "20"),
            ("flight_radar/ring/state", "2"),
            ("flight_radar/sweep/state", "ON"),
        ])
        self.assertNotIn("flight_radar/range/state", c.subs)

    def test_set_topic(self):
        lk, c, _, settings = make()
        poll(lk, c, 0)
        poll(lk, c, 3000)
        c.pubs.clear()
        c.deliver("flight_radar/ring/set", "2.5")
        self.assertEqual(settings, [("ring", 2.5)])
        self.assertEqual(c.states(), [("flight_radar/ring/state", "2.5")])

    def test_garbage_set_ignored(self):
        lk, c, _, settings = make()
        poll(lk, c, 0)
        c.deliver("flight_radar/range/set", "lots")
        self.assertEqual(settings, [])

    def test_planes(self):
        lk, c, planes, _ = make()
        poll(lk, c, 0)
        c.deliver("flight_radar/planes", "A,,,1,2,3,4,5")
        self.assertEqual(planes, ["A,,,1,2,3,4,5"])

    def test_drop_and_reconnect(self):
        lk, c, _, _ = make()
        poll(lk, c, 0)
        poll(lk, c, 3000)
        c.fail_loop = True
        poll(lk, c, 10_000)
        self.assertFalse(lk.connected)
        c.fail_loop = False
        c.fail_connect = True
        for t in range(10_000, 30_000, 100):
            poll(lk, c, t)
        self.assertEqual(c.connects[1:], [12_000, 16_000, 24_000])
        c.fail_connect = False
        c.pubs.clear()
        poll(lk, c, 40_000)
        self.assertTrue(lk.connected)
        self.assertEqual(len(c.states()), 4)  # no restore window on reconnect
        self.assertNotIn("flight_radar/range/state", c.subs)
        self.assertIn("flight_radar/range/set", c.subs)

    def test_publish_while_down(self):
        lk, c, _, _ = make()
        c.fail_connect = True
        poll(lk, c, 0)
        lk.publish_state("range", 5)  # must not raise
        c.fail_connect = False
        poll(lk, c, 2000)
        poll(lk, c, 5000)
        self.assertIn(("flight_radar/range/state", "5"), c.states())

    def test_loop_rate_limited(self):
        lk, c, _, _ = make()
        calls = []
        c.loop = lambda timeout: calls.append(timeout)
        for t in range(0, 1000, 20):
            poll(lk, c, t)
        self.assertEqual(len(calls), 5)


if __name__ == "__main__":
    unittest.main()
