# MQTT link to Home Assistant: plane data in, settings both ways.
# No board imports: code.py passes in a factory that builds a connected-ready
# MiniMQTT client (Wi-Fi up, last will set).

import json

from radar import elapsed, snap_range, snap_ring

NAMES = ("range", "ring", "brightness", "sweep")
PLANES = "flight_radar/planes"
STATUS = "flight_radar/status"
RESTORE_MS = 3000     # after the first connect, read stored settings this long
LOOP_EVERY_MS = 200   # each MQTT check blocks for the loop timeout, so not every frame
LOOP_TIMEOUT = 0.05   # seconds; shorter loses big messages (see the plan's spike results)

DEVICE = {"identifiers": ["flight_radar"], "name": "Flight Radar",
          "manufacturer": "Adafruit", "model": "Matrix Portal M4"}


def state_topic(name):
    return "flight_radar/%s/state" % name


def set_topic(name):
    return "flight_radar/%s/set" % name


def discovery_messages():
    def number(name, title, icon, lo, hi, step, unit=None):
        cfg = {"name": title, "unique_id": "flight_radar_" + name, "icon": icon,
               "command_topic": set_topic(name), "state_topic": state_topic(name),
               "min": lo, "max": hi, "step": step, "mode": "box",
               "availability_topic": STATUS, "device": DEVICE}
        if unit:
            cfg["unit_of_measurement"] = unit
        return ("homeassistant/number/flight_radar_%s/config" % name, json.dumps(cfg))

    sweep = {"name": "Sweep", "unique_id": "flight_radar_sweep", "icon": "mdi:radar",
             "command_topic": set_topic("sweep"), "state_topic": state_topic("sweep"),
             "availability_topic": STATUS, "device": DEVICE}
    return [
        number("range", "Radar range", "mdi:radar", 5, 20, 5, "mi"),
        number("ring", "Inner ring", "mdi:circle-outline", 0.5, 3, 0.5, "mi"),
        number("brightness", "Brightness", "mdi:brightness-6", 5, 255, 1),
        ("homeassistant/switch/flight_radar_sweep/config", json.dumps(sweep)),
    ]


# Turn a payload into a valid setting value, or None if it makes no sense.
def decode(name, payload):
    if name == "sweep":
        p = payload.strip().upper()
        return True if p == "ON" else (False if p == "OFF" else None)
    try:
        v = float(payload)
    except ValueError:
        return None
    if v != v:  # NaN
        return None
    if name == "range":
        return snap_range(v)
    if name == "ring":
        return snap_ring(v)
    if name == "brightness":
        return min(255, max(5, int(v + 0.5)))
    return None


def encode(name, value):
    if name == "sweep":
        return "ON" if value else "OFF"
    if value == int(value):
        return "%d" % value
    return "%.1f" % value


def next_delay(attempt):
    return min(60000, 2000 * 2 ** attempt)


class Link:
    def __init__(self, make_client, on_planes, on_setting, values):
        self.make_client = make_client
        self.on_planes = on_planes
        self.on_setting = on_setting
        self.values = values  # current settings, published after every connect
        self.client = None
        self.connected = False
        self.ever_connected = False
        self.restore_ms = None  # start of the restore window, or None
        self.fail_ms = 0
        self.attempt = -1  # -1: try right away
        self.loop_ms = None
        self.now = 0

    def poll(self, now):
        self.now = now
        if not self.connected:
            if self.attempt < 0 or elapsed(now, self.fail_ms) >= next_delay(self.attempt):
                self._connect(now)
            return
        try:
            if self.restore_ms is not None and elapsed(now, self.restore_ms) >= RESTORE_MS:
                self.restore_ms = None
                for n in NAMES:
                    self.client.unsubscribe(state_topic(n))
                self._publish_all()
            if self.loop_ms is None or elapsed(now, self.loop_ms) >= LOOP_EVERY_MS:
                self.loop_ms = now
                self.client.loop(LOOP_TIMEOUT)
        except Exception as e:  # noqa: BLE001 - any network error: drop and retry later
            self._drop(now, e)

    def publish_state(self, name, value):
        self.values[name] = value
        if not self.connected or self.restore_ms is not None:
            return  # sent after the next connect or when the restore window ends
        try:
            self.client.publish(state_topic(name), encode(name, value), retain=True)
        except Exception as e:  # noqa: BLE001
            self._drop(self.now, e)

    def _connect(self, now):
        try:
            c = self.make_client()
            c.on_message = self._on_message
            c.connect()
            for topic, cfg in discovery_messages():
                c.publish(topic, cfg, retain=True)
            c.publish(STATUS, "online", retain=True)
            c.subscribe(PLANES)
            for n in NAMES:
                c.subscribe(set_topic(n))
            self.client = c
            self.connected = True
            self.attempt = 0
            self.loop_ms = None
            if not self.ever_connected:
                # First connect since boot: read the stored settings before
                # publishing ours, so a reboot doesn't reset them.
                for n in NAMES:
                    c.subscribe(state_topic(n))
                self.restore_ms = now
                self.ever_connected = True
            else:
                self._publish_all()
            print("mqtt: connected")
        except Exception as e:  # noqa: BLE001
            self.attempt += 1
            self.fail_ms = now
            print("mqtt: connect failed:", repr(e))

    def _drop(self, now, err):
        print("mqtt: lost:", repr(err))
        self.connected = False
        self.restore_ms = None
        self.fail_ms = now
        self.attempt = 0
        try:
            self.client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    def _publish_all(self):
        for n in NAMES:
            self.client.publish(state_topic(n), encode(n, self.values[n]), retain=True)

    def _on_message(self, client, topic, msg):
        if topic == PLANES:
            self.on_planes(msg)
            return
        parts = topic.split("/")
        if len(parts) != 3 or parts[1] not in NAMES:
            return
        name, kind = parts[1], parts[2]
        if kind == "state" and self.restore_ms is None:
            return  # only during the restore window
        v = decode(name, msg)
        if v is None:
            return
        self.values[name] = v
        self.on_setting(name, v)
        if kind == "set":
            self.publish_state(name, v)
