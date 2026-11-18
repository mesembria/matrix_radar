# The screen-by-screen scenario behind golden_frames.txt (same steps as the
# old C++ render test). Regenerate the file with: python3 test/cp/make_golden.py
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "circuitpython"))
sys.path.insert(0, HERE)
import radar  # noqa: E402
from radar import Radar  # noqa: E402
from fakes import FakeBitmap  # noqa: E402

RADAR_DATA = (" UA1482,DEN>SFO,B738,-52,31,270,280,18500,BOEING 737-8H4;N172SP,,C172,40,-20,315,100,1400,"
              "CESSNA 172S SKYH;N815SR,,SR22,-60,-50,45,150,4500,;F91307,DEN>MSP,A21N,80,70,30,300,25000,AIRBUS A321NEO")
DETAILS_DATA = ("UA1482,DEN>SFO,B738,-52,31,270,280,18500,BOEING 737-8H4;N172SP,,C172,10,-5,315,100,1400,CESSNA 172S SKYH;"
                "N4417K,,PA28,-8,6,120,95,2200;F91307,DEN>MSP,A21N,80,70,30,300,25000,AIRBUS A321NEO")
GOLDEN = os.path.join(HERE, "golden_frames.txt")


def frames():
    """[(title, rows)] for every screen in the scenario. Updates every 100 ms like the board."""
    r = Radar()
    out = []
    t = [0]

    def run_to(end):
        while t[0] < end:
            t[0] += 100
            r.update(t[0])

    def snap(title, now):
        run_to(now)
        bmp = FakeBitmap()
        r.draw(bmp, now)
        rows = bmp.to_rows(radar.COLORS)
        out.append(("%s (details=%d, ring=%d)" % (title, r.details_now, len(r.ring)), rows))

    snap("no data yet", 1000)
    r.parse(RADAR_DATA, 1000)
    snap("radar, sweep at 36 deg", 2000)
    snap("radar, one full turn", 21000)
    r.set_sweep(False)
    snap("radar, sweep off", 21100)
    r.set_sweep(True)
    r.parse(DETAILS_DATA, 21100)
    snap("details 1", 22000)
    snap("after 6.5 s rotate", 28500)
    r.tap(-1, 28500)
    snap("tap down (next, paused)", 28600)
    r.hold(1, 28600)
    snap("hold -> quiet + toast", 28700)
    snap("quiet radar", 32000)
    snap("stale", 200000)
    return out


def render_text():
    lines = []
    for title, rows in frames():
        lines.append("== " + title)
        lines.extend(rows)
    return "\n".join(lines) + "\n"
