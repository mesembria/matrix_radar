# Flight radar for a 64x32 HUB75 panel on an Adafruit Matrix Portal M4.
# All drawing and screen logic lives here. No board imports, so it also runs
# under desktop Python for the tests in test/cp/.
#
# Data comes from Home Assistant as one string:
#   "id,route,type,x,y,heading,speed,agl;id,route,..."
#   x, y    = tenths of a mile east / north of home
#   heading = degrees, speed = knots, agl = feet above ground

import math

from font import draw_text, text_w

# ---------- Settings you might want to change ----------
LOW_FT = 3000        # under this: low (orange plus sign)
MID_FT = 10000       # under this: mid (green dot with tail)
TOP_FT = 40000       # top of the altitude scale
ROTATE_MS = 6000     # time per plane when several are in the ring
PAUSE_MS = 30000     # rotation pause after a button tap
QUIET_MS = 120000    # radar-only time after a long press
TOAST_MS = 1800      # how long setting messages stay up
STALE_MS = 120000    # no data for this long = "NO DATA"
MAX_COAST_S = 60.0   # stop moving dots this long after the last update
RANGES = (5, 10, 20)
RINGS = (1, 2, 3)

# ---------- Colors (palette indices) ----------
(BLACK, HI_LOW, HI_MID, HI_HIGH, LO_LOW, LO_MID, LO_HIGH,
 WHITE, SOFT, GRAY, DIM, SWEEP, SWEEP_TAIL, BAR_OFF) = range(14)
COLORS = [
    (0, 0, 0),
    (255, 110, 0),    # low: orange
    (70, 210, 40),    # mid: green
    (40, 100, 255),   # high: blue
    (80, 32, 0),
    (16, 60, 10),
    (10, 26, 80),
    # Radar, sweep and text: a cool green, so green (mid) planes still stand out.
    (120, 255, 150),  # "white": home dot, plane id, messages
    (60, 190, 110),   # "soft": route line
    (25, 130, 70),    # "gray": inner ring, range, labels
    (8, 50, 26),      # "dim": outer ring
    (0, 110, 55),     # sweep
    (0, 40, 20),      # sweep tail
    (10, 35, 20),     # bar off
]
BAND_HI = (HI_LOW, HI_MID, HI_HIGH)
BAND_LO = (LO_LOW, LO_MID, LO_HIGH)

# After the sweep passes, a plane fades in steps until the next pass.
# Faded copies of the six band colors follow the base colors (indices 14..31).
FADE = (1.0, 0.7, 0.5, 0.33)
_BANDS = BAND_HI + BAND_LO
for _c in _BANDS:
    for _f in FADE[1:]:
        COLORS.append(tuple(int(v * _f) for v in COLORS[_c]))


def faded(c, level):
    if level == 0:
        return c
    return 14 + _BANDS.index(c) * 3 + level - 1


# The M4 has no hardware brightness, so scale the colors. Lit stays lit.
def palette_colors(brightness):
    out = []
    for rgb in COLORS:
        c = 0
        for v in rgb:
            s = v * brightness // 255
            c = (c << 8) | (max(1, s) if v else 0)
        out.append(c)
    return out


# supervisor.ticks_ms() wraps at 2**29. Every time difference goes through elapsed().
TICKS_PERIOD = 1 << 29


def elapsed(now, then):
    return (now - then) % TICKS_PERIOD


# Round half away from zero, like C lroundf, so pixels match the C++ version.
def lround(v):
    return int(v + 0.5) if v >= 0 else -int(-v + 0.5)


def px(bmp, x, y, c):
    ix, iy = lround(x), lround(y)
    if 0 <= ix < 64 and 0 <= iy < 32:
        bmp[ix, iy] = c


# One sweep turn, tuned so a typical small plane (~110 kt) moves about a pixel
# per turn. Capped at 20 s, the rate new data arrives.
def sweep_period(range_mi):
    return 10000 if range_mi <= 5 else 20000


def band(agl):
    return 0 if agl < LOW_FT else (1 if agl < MID_FT else 2)


def fmt_mi(v):
    if abs(v - round(v)) < 0.05:
        return "%d MI" % round(v)
    return "%.1f MI" % v


def snap_range(v):
    return min((5, 10, 15, 20), key=lambda r: abs(r - v))


def snap_ring(v):
    return min(3.0, max(0.5, round(v * 2) / 2))


def step_list(values, cur, up):
    if up > 0:
        for v in values:
            if v > cur + 0.01:
                return v
        return values[-1]
    for v in reversed(values):
        if v < cur - 0.01:
            return v
    return values[0]


class Plane:
    def __init__(self, fields):
        self.id = fields[0] or "?"
        self.route = fields[1]
        self.type = fields[2]
        self.x0 = float(fields[3]) / 10  # miles east / north of home when the data arrived
        self.y0 = float(fields[4]) / 10
        self.hdg = int(fields[5])
        self.spd = int(fields[6])
        self.agl = max(0, int(fields[7]))
        self.model = fields[8] if len(fields) > 8 else ""  # e.g. "CESSNA 172", from newer HA packages
        self.x, self.y, self.d, self.bearing = self.x0, self.y0, 0.0, 0.0


class Radar:
    def __init__(self):
        self.range_mi = 10.0
        self.ring_mi = 2.0
        self.sweep_on = True
        self.planes = []
        self.have_data = False
        self.data_ms = 0
        self.ring = []  # ids inside the inner ring, in arrival order
        self.idx = 0
        self.shown_ms = 0
        self.details_now = False
        # Timers: start time, or None when off.
        self.pause_ms = None
        self.quiet_ms = None
        self.toast_ms = None
        self.toast_lines = ("", "")
        self._ring_key = None
        self.sweep_deg = 0.0
        self.sweep_ms = None  # time of the last sweep step
        self.painted = {}  # id -> (x, y, ms): where the sweep last saw the plane
        self._ahead = {}
        self._inner = []

    # True while a timer is running; switches itself off when it runs out.
    def _running(self, name, dur, now):
        start = getattr(self, name)
        if start is not None and elapsed(now, start) >= dur:
            setattr(self, name, None)
            start = None
        return start is not None

    def stale(self, now):
        return not self.have_data or elapsed(now, self.data_ms) > STALE_MS

    # ---------- Data in ----------
    def parse(self, s, now):
        out = []
        for rec in s.split(";"):
            rec = rec.strip()
            if not rec:
                continue
            f = [x.strip() for x in rec.split(",")]
            if len(f) < 8:
                continue
            try:
                out.append(Plane(f))
            except ValueError:
                continue  # a field that isn't a number: skip the plane
        self.planes = out
        self.have_data = True
        self.data_ms = now

    # ---------- Per-frame updates ----------
    def update(self, now):
        if self.have_data and self.stale(now):
            self.planes = []
        self._update_positions(now)
        self._advance_sweep(now)
        self._update_ring(now)
        self._rotate(now)
        quiet = self._running("quiet_ms", QUIET_MS, now)
        self.details_now = bool(self.ring) and not quiet

    def _update_positions(self, now):
        dt = min(elapsed(now, self.data_ms) / 1000, MAX_COAST_S) if self.have_data else 0.0
        for p in self.planes:
            miles = p.spd * 1.15078 / 3600 * dt  # knots to miles moved
            h = math.radians(p.hdg)
            p.x = p.x0 + math.sin(h) * miles
            p.y = p.y0 + math.cos(h) * miles
            p.d = math.sqrt(p.x * p.x + p.y * p.y)
            p.bearing = (math.degrees(math.atan2(p.x, p.y)) + 360) % 360

    # Move the sweep on and note which planes it crossed. A plane is only
    # redrawn where the sweep last saw it. "Ahead" is how far the sweep still
    # has to turn to reach a plane; it wraps past 0 when the sweep crosses the
    # plane, whichever way the plane itself is moving.
    def _advance_sweep(self, now):
        step = 0.0
        if self.sweep_ms is not None:
            step = elapsed(now, self.sweep_ms) * 360 / sweep_period(self.range_mi)
        self.sweep_ms = now
        cur = self.sweep_deg = (self.sweep_deg + step) % 360
        if not self.sweep_on:
            self.painted = {}
            self._ahead = {}
            return
        painted, ahead = {}, {}
        for p in self.planes:
            if p.d > self.range_mi:
                continue
            a = (p.bearing - cur) % 360
            before = self._ahead.get(p.id)
            ahead[p.id] = a
            crossed = before is not None and (a == 0 or 0 < before < 180 <= a)
            if step >= 360 or crossed:
                painted[p.id] = (p.x, p.y, now)
            elif p.id in self.painted:
                painted[p.id] = self.painted[p.id]
        self.painted, self._ahead = painted, ahead

    # 0 right after the sweep passed, up to 3 just before the next pass;
    # None if the sweep hasn't reached the plane yet.
    def fade_level(self, pid, now):
        got = self.painted.get(pid)
        if got is None:
            return None
        return min(3, elapsed(now, got[2]) * 4 // sweep_period(self.range_mi))

    def find(self, pid):
        for p in self.planes:
            if p.id == pid:
                return p
        return None

    def _update_ring(self, now):
        cur = self.ring[self.idx] if self.idx < len(self.ring) else ""
        old_idx = self.idx
        # Keep planes still inside (10% slack so a plane on the edge doesn't flicker).
        nxt = []
        for pid in self.ring:
            p = self.find(pid)
            if p and p.d <= self.ring_mi * 1.1:
                nxt.append(pid)
        # Add newcomers at the end, closest first if several arrive together.
        fresh = [p for p in self.planes if p.d < self.ring_mi and p.id not in nxt]
        fresh.sort(key=lambda p: p.d)
        nxt.extend(p.id for p in fresh)

        self.ring = nxt
        if not nxt:
            self.idx = 0
            return
        if cur and cur in nxt:
            self.idx = nxt.index(cur)  # stay on the plane we were showing
        else:
            self.idx = min(old_idx, len(nxt) - 1)  # it left: show the next one
            self.shown_ms = now

    def _rotate(self, now):
        if len(self.ring) < 2 or self._running("pause_ms", PAUSE_MS, now):
            self.shown_ms = now  # fresh 6 seconds once rotation resumes
            return
        if elapsed(now, self.shown_ms) >= ROTATE_MS:
            self.idx = (self.idx + 1) % len(self.ring)
            self.shown_ms = now

    # ---------- Toasts ----------
    def _show_toast(self, a, b, now):
        self.toast_lines = (a, b)
        self.toast_ms = now

    def toast(self, now):
        return self.toast_lines if self._running("toast_ms", TOAST_MS, now) else None

    # ---------- Buttons ----------
    # up = +1 for the Up button, -1 for Down. Return the setting that changed, if any.
    def tap(self, up, now):
        if self.details_now and self.ring:  # Up = previous plane, Down = next
            self.idx = (self.idx + (-1 if up > 0 else 1)) % len(self.ring)
            self.shown_ms = now
            self.pause_ms = now
            return None
        self.range_mi = step_list(RANGES, self.range_mi, up)  # Up = zoom out
        self._show_toast("RANGE", fmt_mi(self.range_mi), now)
        return {"range": self.range_mi}

    def hold(self, up, now):
        if self.details_now:  # back to the radar for a while
            self.quiet_ms = now
            self._show_toast("RADAR", "%d MIN" % (QUIET_MS // 60000), now)
            return None
        self.ring_mi = step_list(RINGS, self.ring_mi, up)  # Up = bigger ring
        self._show_toast("RING", fmt_mi(self.ring_mi), now)
        return {"ring": self.ring_mi}

    def toggle_sweep(self, now):
        self.sweep_on = not self.sweep_on
        self._show_toast("SWEEP", "ON" if self.sweep_on else "OFF", now)
        return {"sweep": self.sweep_on}

    # ---------- Settings from Home Assistant (no toast) ----------
    def set_range(self, v):
        self.range_mi = snap_range(v)

    def set_ring(self, v):
        self.ring_mi = snap_ring(v)

    def set_sweep(self, on):
        self.sweep_on = bool(on)

    # ---------- Screens ----------
    def draw(self, bmp, now):
        bmp.fill(BLACK)
        if self.details_now:
            self._draw_details(bmp, now)
        else:
            self._draw_radar(bmp, now)

    def _ring_points(self):
        key = (self.range_mi, self.ring_mi)
        if key != self._ring_key:
            ir = max(1.5, self.ring_mi / self.range_mi * PR)
            self._inner = circle_points(ir, 15 if ir > 4 else 30)
            self._ring_key = key
        return self._inner

    def _draw_radar(self, bmp, now):
        for x, y in OUTER:
            bmp[x, y] = DIM
        for x, y in self._ring_points():
            bmp[x, y] = GRAY

        if self.sweep_on:
            sw = self.sweep_deg
            for ang, c in ((sw - 8, SWEEP_TAIL), (sw, SWEEP)):
                s, co = math.sin(math.radians(ang)), math.cos(math.radians(ang))
                for k in range(2, PR):
                    px(bmp, CX + s * k, CY - co * k, c)

        rng = self.range_mi
        vis = [p for p in self.planes if p.d <= rng]
        vis.sort(key=lambda p: -p.agl)  # high planes first so low ones end up on top
        count = [0, 0, 0]
        for p in vis:
            b = band(p.agl)
            count[b] += 1
            if not self.sweep_on:  # nothing to reveal it: draw it live
                mark(bmp, CX + p.x / rng * PR, CY - p.y / rng * PR, b, p.hdg)
                continue
            got = self.painted.get(p.id)
            if got is None:
                continue  # the sweep hasn't reached it yet
            mark(bmp, CX + got[0] / rng * PR, CY - got[1] / rng * PR, b, p.hdg,
                 self.fade_level(p.id, now))
        bmp[CX, CY] = WHITE  # home

        draw_text(bmp, 0, 0, "%d" % round(rng), GRAY)  # range in miles, top left

        if self.quiet_ms is not None:  # pause symbol, bottom left: details are snoozed
            for y in range(27, 32):
                bmp[0, y] = GRAY
                bmp[2, y] = GRAY

        t = self.toast(now)
        if t:
            right_message(bmp, t[0], t[1], WHITE)
            return
        if self.stale(now):
            right_message(bmp, "NO", "DATA", GRAY)
            return

        # Altitude scale along the right edge: dim section per band,
        # a bright tick for every plane at its height.
        for y in range(20, 30):
            bmp[63, y] = LO_LOW
        for y in range(11, 20):
            bmp[63, y] = LO_MID
        for y in range(2, 11):
            bmp[63, y] = LO_HIGH
        for p in vis:
            y = alt_y(p.agl)
            c = BAND_HI[band(p.agl)]
            for x in range(60, 63):
                px(bmp, x, y, c)
        # Count and marker just inside each section.
        for b, cy in enumerate((24, 15, 6)):
            mark(bmp, 56, cy, b, 270)
            n = "%d" % count[b]
            draw_text(bmp, 53 - text_w(n), cy - 2, n, BAND_HI[b])

    def _draw_details(self, bmp, now):
        p = self.find(self.ring[self.idx])
        if not p:
            return
        b = band(p.agl)
        n = len(self.ring)

        # Left: ID (and "n/N"), route or speed, height. About 10 characters wide.
        pid = p.id
        if n > 1:
            s = "%d/%d" % (self.idx + 1, n)
            x = LEFT_END + 1 - text_w(s)
            draw_text(bmp, x, 1, s, GRAY)
            pid = pid[:(x - 2) // 4]
        draw_text(bmp, 1, 1, pid[:LEFT_CHARS], WHITE)

        line2 = p.route
        if not line2 and p.spd > 0:
            line2 = "%dKT" % p.spd
        draw_text(bmp, 1, 8, line2[:LEFT_CHARS], SOFT)
        draw_text(bmp, 1, 15, "%dFT" % p.agl, BAND_HI[b])

        # Right: mini radar. House in the middle, edge = inner ring (with its slack),
        # the plane as a dot with a tail pointing where it came from.
        for x, y in MINI_RING:
            bmp[x, y] = DIM
        bmp[MCX, MCY] = WHITE
        k = MR / (self.ring_mi * 1.1)
        px_, py_ = MCX + p.x * k, MCY - p.y * k
        h = math.radians(p.hdg)
        for back in (2, 1):
            px(bmp, px_ - math.sin(h) * back, py_ + math.cos(h) * back, BAND_LO[b])
        px(bmp, px_, py_, BAND_HI[b])

        # Full width: what kind of plane it is.
        draw_text(bmp, 1, 22, (p.model or p.type)[:16], SOFT)

        # Bottom bar: how close to the house. Full overhead, empty at the ring's edge.
        # Gray while rotation is paused.
        paused = n > 1 and self._running("pause_ms", PAUSE_MS, now)
        w = lround(64 * max(0.0, min(1.0, 1 - p.d / self.ring_mi)))
        on = GRAY if paused else BAND_HI[b]
        for x in range(64):
            bmp[x, 30] = on if x < w else BAR_OFF


# ---------- Drawing helpers ----------
CX, CY, PR = 15, 16, 14  # radar center and radius in pixels


def circle_points(r, step):
    pts = []
    for a in range(0, 360, step):
        x = lround(CX + math.sin(math.radians(a)) * r)
        y = lround(CY - math.cos(math.radians(a)) * r)
        if 0 <= x < 64 and 0 <= y < 32:
            pts.append((x, y))
    return pts


OUTER = circle_points(PR, 4)

# Details page layout.
LEFT_END = 41              # last column for the left-hand text
LEFT_CHARS = (LEFT_END + 1) // 4
MCX, MCY, MR = 53, 10, 9   # mini radar center and radius


def _mini_ring():
    pts = []
    for a in range(0, 360, 15):
        p = (lround(MCX + math.sin(math.radians(a)) * MR), lround(MCY - math.cos(math.radians(a)) * MR))
        if p not in pts:
            pts.append(p)
    return pts


MINI_RING = _mini_ring()


# Plane marker. Shape and color both say the height band.
def mark(bmp, x, y, b, hdg, level=0):
    h = math.radians(hdg)
    hi, lo = faded(BAND_HI[b], level), faded(BAND_LO[b], level)
    if b == 0:  # low: plus sign with a tail
        px(bmp, x - math.sin(h) * 2.2, y + math.cos(h) * 2.2, lo)
        for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
            px(bmp, x + dx, y + dy, hi)
    elif b == 1:  # mid: dot with a tail
        px(bmp, x - math.sin(h) * 1.4, y + math.cos(h) * 1.4, lo)
        px(bmp, x, y, hi)
    else:  # high: single dot
        px(bmp, x, y, hi)


# Altitude scale on the right: ground at the bottom, each band gets its own section.
def alt_y(agl):
    if agl < LOW_FT:
        return 29.0 - 9.0 * agl / LOW_FT
    if agl < MID_FT:
        return 19.0 - 8.0 * (agl - LOW_FT) / (MID_FT - LOW_FT)
    return 10.0 - 8.0 * min(1.0, (agl - MID_FT) / (TOP_FT - MID_FT))


def right_message(bmp, a, b, c):
    draw_text(bmp, 33 + (31 - text_w(a)) // 2, 8, a, c)
    draw_text(bmp, 33 + (31 - text_w(b)) // 2, 16, b, c)
