# Up/Down buttons: taps, holds, and both together. Events fire on release.
#   ("tap", 1) / ("tap", -1)    pressed 20 to 600 ms
#   ("hold", 1) / ("hold", -1)  pressed 700 ms to 5 s
#   ("both",)                   both down together for 100 ms or more

from radar import elapsed

DEBOUNCE_MS = 20
TAP_MS = (20, 600)
HOLD_MS = (700, 5000)
BOTH_MS = 100


class _Button:
    def __init__(self, up):
        self.up = up
        self.down = False
        self.change_ms = None  # when the raw reading started to differ
        self.press_ms = 0

    # Returns the time of a settled press or release, or None.
    def settle(self, raw, now):
        if raw == self.down:
            self.change_ms = None
            return None
        if self.change_ms is None:
            self.change_ms = now
            return None
        if elapsed(now, self.change_ms) < DEBOUNCE_MS:
            return None
        self.down = raw
        t, self.change_ms = self.change_ms, None
        return t

    def event(self, release_ms):
        held = elapsed(release_ms, self.press_ms)
        if TAP_MS[0] <= held <= TAP_MS[1]:
            return ("tap", self.up)
        if HOLD_MS[0] <= held <= HOLD_MS[1]:
            return ("hold", self.up)
        return None


class Buttons:
    def __init__(self):
        self.btns = (_Button(1), _Button(-1))
        self.both_ms = None  # when both went down together
        self.combo = False   # this press counts as "both"
        self.pending = []

    def update(self, up, down, now):
        for b, raw in zip(self.btns, (up, down)):
            t = b.settle(raw, now)
            if t is None:
                continue
            if b.down:
                b.press_ms = t
            elif not self.combo:
                ev = b.event(t)
                if ev:
                    self.pending.append(ev)

        if all(b.down for b in self.btns):
            if self.both_ms is None:
                self.both_ms = now
            if elapsed(now, self.both_ms) >= BOTH_MS:
                self.combo = True
        else:
            self.both_ms = None
            if self.combo and not any(b.down for b in self.btns):
                self.combo = False
                self.pending.append(("both",))

        return self.pending.pop(0) if self.pending else None
