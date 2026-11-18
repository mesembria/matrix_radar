# Sweep reveal, fade, and new details page: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Planes on the radar move only when the sweep crosses them and fade between passes; the details page gets a mini radar, a plane type name line and a closeness bar.

**Architecture:** All logic stays in `circuitpython/radar.py` (pure Python, desktop-testable). Sweep state moves from draw time into `Radar.update()` so it can be tested without pixels. HA adds the aircraft model as a 9th `packed` field. The throwaway spike (`scratchpad/fade_spike/radar.py`) shows the idea but is not reused as code.

**Tech Stack:** CircuitPython 10.3.1 on the Matrix Portal M4; desktop `unittest`; HA Jinja template tested with `uv run --with pyyaml --with jinja2`.

**Spec:** `docs/superpowers/specs/2026-10-29-sweep-fade-and-details-design.md`. Earlier plan and ledger: `docs/superpowers/plans/2026-10-29-matrix-portal-m4-port.md`, `.superpowers/sdd/2026-10-29-matrix-portal-m4-port/progress.md`.

## Global Constraints
- Sweep period: 5 mi = 10000 ms; 10, 15 and 20 mi = 20000 ms.
- Fade levels after a pass: `FADE = (1.0, 0.7, 0.5, 0.33)`, level = `min(3, int(age / period * 4))`. Never fully dark.
- Sweep off: marks drawn live (coasted position, full brightness), as today.
- Altitude scale, counts and details stay live.
- Type name: at most 16 characters, `A-Z 0-9 - space`, upper case; fall back to the type code.
- Board accepts `packed` records with 8 or 9 fields.
- Frame rate ≥ 8 fps on the board with the sweep on.
- Radar parts green, plane bands orange/green/blue (`COLORS[1:7]` unchanged).
- Tests: `python3 -W error -m unittest discover -s test/cp` and `uv run --with pyyaml --with jinja2 python3 test/template_test.py`.
- No git repo: no commit steps. Ledger in `.superpowers/sdd/2026-10-29-sweep-fade-and-details/progress.md`.
- Text style: plain short words, no em dashes.

## Review Focus
1. **Long frame gap.** The board freezes for seconds while MQTT reconnects. Expect every plane to count as swept when the sweep advanced 360° or more in one update (Task 2 test).
2. **Zoom change mid-turn.** Changing the range changes the period. Expect the sweep angle to continue from where it was, no jump, no planes skipped or double-revealed (Task 2 test).
3. **Plane at exactly 0°/360°** and sweeps that wrap past north. Expect it to be revealed once per turn (Task 2 test).
4. **Plane leaves and comes back.** Expect its stored position to be dropped when it leaves the range, and it to reappear only when swept again (Task 2 test).
5. **Odd model text from HA.** Commas, semicolons, lower case, very long names, missing model. Expect a clean 16-char upper-case name or an empty field, never a broken record (Task 1 test).

---

### Task 1: HA sends the model name

**Files:** Modify `homeassistant/flight_radar.yaml` (packed template), `test/template_test.py`.

- [ ] **Step 1: Failing test.** In `template_test.py`, give the sample flights `aircraft_model` values `"Boeing 737-8H4"`, `"Cessna 172S Skyhawk SP, with; junk"`, `None`; assert each `packed` record has 9 fields; field 9 equals `"BOEING 737-8H4"`, `"CESSNA 172S SKYH"` (cleaned, then cut to 16), and `""`; no record contains an extra `,` or `;`. Assert 40 planes with 16-char names and 7-char ids stay under 2,600 characters.
- [ ] **Step 2: Run, expect failure** (8 fields).
- [ ] **Step 3: Implement.** Append `(f.aircraft_model or '') | string | upper | regex_replace('[^A-Z0-9 -]', '') | trim` cut to 16 with `[:16]` and trimmed again, as the 9th field.
- [ ] **Step 4: Run, expect pass.** Existing output otherwise unchanged.

### Task 2: Sweep state in `Radar.update()`

**Files:** Modify `circuitpython/radar.py`; Test `test/cp/test_sweep.py` (new).

**Interfaces:**
- Produces: `sweep_period(range_mi) -> int` (ms); `Radar.sweep_deg: float` (0..360, advanced in `update` by `elapsed * 360 / period` since the last update); `Radar.painted: dict[str, tuple[float, float, int]]` (id → x, y, ms when last swept); `Radar.fade_level(pid, now) -> int | None` (None = not revealed yet); `Plane.bearing` (degrees from north, set with `x, y, d`).
- Rules: a plane within `range_mi` is swept when its bearing lies in the arc `(prev, cur]` going clockwise, or when the advance was ≥ 360°. Swept → `painted[id] = (x, y, now)`. Ids not within range are removed from `painted`. When `sweep_on` is False, `painted` is cleared and not used.

- [ ] **Step 1: Failing tests** in `test_sweep.py` (data `"E,,,50,0,90,0,1500"`: due east, 5 mi, not moving; range 10):
  - `test_period`: `sweep_period(5) == 10000`, `sweep_period(10) == sweep_period(15) == sweep_period(20) == 20000`.
  - `test_hidden_until_swept`: update every 100 ms from 0; `fade_level("E", t)` is None for t < 5000, 0 at the first update with t ≥ 5000.
  - `test_moves_only_on_pass`: plane `"M,,,0,-50,90,360,1500"` (moving east fast); `painted["M"]` x stays the same between passes and changes after the next pass.
  - `test_fade_steps`: after the reveal at ~5000: level 0 at +1000, 1 at +5500, 2 at +10500, 3 at +15500.
  - `test_wrap_north`: plane `"N,,,0,50,0,0,1500"` (bearing 0) revealed exactly once per turn over 3 turns.
  - `test_long_gap`: update at 0, then at 25000 → every plane in range is in `painted` with ms 25000.
  - `test_zoom_mid_turn`: at sweep_deg ≈ 90 change range 10 → 5; next update 100 ms later → `sweep_deg ≈ 90 + 3.6`, not a jump.
  - `test_leave_and_return`: plane revealed, then data puts it outside range → not in `painted`; back inside → `fade_level` None until swept.
  - `test_sweep_off_clears`: `set_sweep(False)` → `painted == {}` after update.
- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.** Remove `SWEEP_MS`. Keep the existing `test_radar.py` passing.
- [ ] **Step 4: Run whole suite, expect pass.**

### Task 3: Draw the revealed, fading marks

**Files:** Modify `circuitpython/radar.py`, `circuitpython/code.py` (bitmap and palette size 32); Test `test/cp/test_render.py`.

**Interfaces:**
- Consumes: Task 2.
- Produces: `FADE`, `faded(c: int, level: int) -> int` (index of the faded copy of a band color; level 0 → `c`), `COLORS` grows to 32 entries (14 base + 6 band colors × 3 fade levels), `mark(bmp, x, y, b, hdg, level=0)`.

- [ ] **Step 1: Failing tests.**
  - `test_palette_size`: `len(radar.COLORS) == 32`; `faded(HI_LOW, 2)` has RGB `int(v * 0.5)` of `COLORS[HI_LOW]`.
  - `test_radar_draws_painted_position`: sweep on, plane revealed at t, moved by new data; drawn pixel is at the painted x/y, not the new one, in `faded(band, level)`.
  - `test_unrevealed_not_drawn`, `test_sweep_off_draws_live` (marks at coasted position, level 0).
  - Counts on the altitude scale include unrevealed planes (they stay live).
  - Replace the C++ golden comparison: `golden_frames.txt` becomes a Python snapshot of the same scenario (radar frames with sweep off so they stay comparable to the old C++ frames minus sweep pixels; details frames from Task 4). Add `test/cp/make_golden.py` to regenerate it. Ruling to ledger: C++ parity ends here because the design now differs on purpose.
- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect pass.**

### Task 4: New details page

**Files:** Modify `circuitpython/radar.py`; Test `test/cp/test_details.py` (new).

**Interfaces:**
- Consumes: `Plane.model` (str, "" when absent; parsed from an optional 9th field).
- Produces: layout constants `MCX, MCY, MR = 53, 10, 9` (mini radar center, radius); left text area x 1..41; lines at y 1 (ID), 8 (route or speed), 15 (height); type line at y 22 from x 1; bar at y 30.

- [ ] **Step 1: Failing tests** (`test_details.py`, ring 2 mi):
  - `test_parse_model`: 9-field record → `model == "CESSNA 172"`; 8-field record → `model == ""`.
  - `test_type_line`: model shown at y 22; empty model → type code; 20-char model → first 16 chars.
  - `test_mini_radar`: house pixel `(53, 10)` is WHITE; plane at x 0, y 1.0 mi → band HI pixel at `(53, 6)` (`lround(10 - 0.5 * 9)`); faint ring pixels at radius 9 in DIM.
  - `test_arrow_points_along_heading`: heading 90 → a band pixel at `(54, 6)` or `(55, 6)` and none at `(52, 6)`/`(51, 6)` (head ahead of the plane).
  - `test_closeness_bar`: d = 0.5 mi of 2 → x < 48 band HI, x ≥ 48 BAR_OFF; d ≥ 2 → all BAR_OFF; paused → lit part GRAY.
  - `test_left_text_fits`: no left-area text pixel at x ≥ 42; with 2 planes, `"1/2"` ends at x 41 and the ID is cut so it doesn't touch it.
  - `test_no_distance_line`: nothing lit in rows 22..26 except the type line text; no "MI" text anywhere.
- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.** Mini radar: faint ring, house dot, plane mark as a 3-pixel arrow (head at the plane's position, two pixels behind along the reverse heading in band LO). Plane position scaled so ring_mi × 1.1 maps to MR.
- [ ] **Step 4: Run whole suite, expect pass.** Regenerate the snapshot with `make_golden.py`, print the details frames and check them by eye.

### Task 5: On the board, with Philippe

- [ ] **Step 1: Deploy** `radar.py`, `code.py` (and font, buttons, link unchanged) to `/Volumes/CIRCUITPY/`. Console shows no errors.
- [ ] **Step 2: Message size.** Publish a 2,600-char `packed` with `mosquitto_pub`/paho 5 times; all arrive (`planes` count in the console line matches).
- [ ] **Step 3: Philippe pastes the updated HA package** (`pbcopy < homeassistant/flight_radar.yaml`), reloads Template entities. Check `flight_radar/planes` on the broker has 9-field records with names.
- [ ] **Step 4: Check together:** fps from the console ≥ 8 with real traffic; sweep reveal and fade; details page readability; names present.

### Task 6: Docs

- [ ] **Step 1:** README: radar paragraph (sweep reveals, fade, speeds by zoom), details list (mini radar, type line, closeness bar; drop distance line and countdown), data format note (9th field). CLAUDE.md: data format, design decisions (sweep, fade, details layout), testing (snapshot + `make_golden.py`), status.
- [ ] **Step 2:** `grep -n "—" README.md CLAUDE.md` returns nothing.
