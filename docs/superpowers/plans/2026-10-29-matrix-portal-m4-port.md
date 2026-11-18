# Flight radar on the Matrix Portal M4: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the flight radar on the Matrix Portal M4 in CircuitPython, with planes and settings over MQTT and a sweep on/off toggle.

**Architecture:** Pure-Python modules (`font.py`, `radar.py`, `buttons.py`, `link.py`) hold all logic and drawing and run under desktop CPython for tests. `code.py` is thin glue to the hardware: `rgbmatrix` + `displayio` bitmap, `digitalio` buttons, ESP32 AirLift + MiniMQTT. HA publishes the existing `packed` string to a retained MQTT topic; the board exposes range, ring, brightness and sweep through MQTT discovery.

**Tech Stack:** CircuitPython (current stable for `matrixportal_m4`), `adafruit_esp32spi`, `adafruit_minimqtt`, `adafruit_connection_manager`, built-in `rgbmatrix`/`framebufferio`/`displayio`. Desktop tests: Python 3 `unittest` (pytest isn't installed), C++ render test for golden frames. HA side: YAML package, tested with `uv run --with pyyaml --with jinja2`.

**Spec:** `docs/superpowers/specs/2026-10-29-matrix-portal-m4-port-design.md`. Behavior reference: `esphome/flight_radar.h` and CLAUDE.md "Design decisions".

## Global Constraints
- Same constants as `flight_radar.h`: LOW_FT 3000, MID_FT 10000, TOP_FT 40000, ROTATE_MS 6000, PAUSE_MS 30000, QUIET_MS 120000, TOAST_MS 1800, STALE_MS 120000, SWEEP_MS 4000, MAX_COAST_S 60, RANGES (5, 10, 20), RINGS (1, 2, 3). Same colors, same pixel layout.
- Defaults when nothing is stored: range 10 mi, ring 2 mi, brightness 128, sweep on.
- HA entity limits: range 5 to 20 step 5; ring 0.5 to 3 step 0.5; brightness 5 to 255 step 1; sweep switch `ON`/`OFF`.
- Topics: `flight_radar/planes`, `flight_radar/status` (`online`/`offline`, last will), `flight_radar/<name>/state` and `flight_radar/<name>/set` for name in `range`, `ring`, `brightness`, `sweep`. Discovery prefix `homeassistant`.
- No night dimming anywhere.
- Times are integer milliseconds from `supervisor.ticks_ms()`, which wraps every 2^29 ms (~6.2 days). Every time difference goes through `radar.elapsed(now, then)`. Never use `time.monotonic()` for timing (float precision decays).
- `radar.py`, `font.py`, `buttons.py`, `link.py` import nothing board-specific (`math`, `json` only), so desktop tests import them directly.
- Credentials live only in `esphome/secrets.yaml` (Wi-Fi) and the board's `settings.toml`. Never copy them into repo docs, plans or test files.
- User-facing text (README, toasts): plain short words, active voice, no em dashes.
- `esphome/` is not touched.
- The project is not a git repo. There are no commit steps; do not run `git init` unless Philippe asks.

## Review Focus
1. **Empty sky.** With no planes, `packed` stays `""` and HA never fires a state change, so the panel would show NO DATA. Expect the radar with zero counts. HA must also publish on a timer (Task 8 test).
2. **Garbage from MQTT or HA.** Non-numeric fields in a plane record, records with fewer than 8 fields, a setting payload like `abc`, `7`, `999`. Expect bad records skipped, good ones kept, settings snapped/clamped or ignored, no exception (Tasks 3 and 6 tests).
3. **Network drops.** Wi-Fi or broker gone mid-run. Expect the radar keeps animating, dots coast then stop, NO DATA after 2 min, reconnect with backoff, states republished after reconnect (Task 6 tests).
4. **Tick wrap after ~6 days of uptime.** Expect timers, coasting and rotation to keep working across the wrap (Task 3 test).
5. **Both-button release order.** Up and Down pressed together, released one at a time. Expect only the sweep toggle, never also a tap or hold of the button released last (Task 5 test).

---

### Task 1: Back up the board and install current CircuitPython

**Files:**
- Create: `backup/weather-display/` (copy of the whole `CIRCUITPY` drive)
- Create: `circuitpython/settings.toml.example`

**Interfaces:**
- Produces: a board on current stable CircuitPython with libraries `adafruit_esp32spi`, `adafruit_minimqtt`, `adafruit_connection_manager` in `lib/`, and a `settings.toml` with keys `CIRCUITPY_WIFI_SSID`, `CIRCUITPY_WIFI_PASSWORD`, `MQTT_BROKER`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASSWORD`.

- [ ] **Step 1: Copy the drive.** `rsync -a --exclude .fseventsd --exclude .Trashes /Volumes/CIRCUITPY/ backup/weather-display/`. Check: `diff -rq` against the drive shows only the excluded items.
- [ ] **Step 2: Get the UF2.** Download the current stable CircuitPython UF2 for `matrixportal_m4` from circuitpython.org into the scratchpad.
- [ ] **Step 3: Enter the bootloader.** Ask Philippe to double-tap RESET. Check: a `MATRIXBOOT` volume appears. Copy the UF2 onto it. Check: `CIRCUITPY` comes back and `boot_out.txt` shows the new version.
- [ ] **Step 4: Install libraries.** `uv tool run circup install adafruit_esp32spi adafruit_minimqtt adafruit_connection_manager`. Check: the three are listed in `/Volumes/CIRCUITPY/lib`.
- [ ] **Step 5: Settings.** Write `circuitpython/settings.toml.example` with the six keys and placeholder values. Ask Philippe for broker host, port, user and password. Write the real `settings.toml` on the board only, taking Wi-Fi from `esphome/secrets.yaml`.

### Task 2: Hardware spike (throwaway): frame rate, memory, MQTT loop cost

Decides three numbers later tasks use. Delete the spike file after.

**Files:**
- Create: `circuitpython/spike.py` (copied to the board as `code.py`)
- Modify: this plan, "Spike results" line at the end of the task

- [ ] **Step 1: Write the spike.** Set up `rgbmatrix.RGBMatrix(width=64, height=32, bit_depth=N, rgb_pins=[board.MTX_R1, board.MTX_G1, board.MTX_B1, board.MTX_R2, board.MTX_G2, board.MTX_B2], addr_pins=[board.MTX_ADDRA, board.MTX_ADDRB, board.MTX_ADDRC, board.MTX_ADDRD], clock_pin=board.MTX_CLK, latch_pin=board.MTX_LAT, output_enable_pin=board.MTX_OE)`, `framebufferio.FramebufferDisplay(..., auto_refresh=False)`, a 64x32 `displayio.Bitmap` with 14 colors. Each frame: `fill(0)`, draw ~300 pixels with `math.sin`/`cos` (outer ring, inner ring, sweep, 20 plane dots), `display.refresh()`. Connect Wi-Fi via `adafruit_esp32spi` (pins `board.ESP_CS`, `board.ESP_BUSY`, `board.ESP_RESET`), print `esp.firmware_version`, connect MiniMQTT, subscribe `flight_radar/planes`, call `mqtt.loop(timeout=T)` every frame. Print fps and `gc.mem_free()` every 5 s.
- [ ] **Step 2: Measure.** Run with bit_depth 4 and 5, and the smallest `socket_timeout`/`loop(timeout)` pair MiniMQTT accepts. Read output over serial (`/dev/cu.usbmodem*`). Publish a 1,600-char test payload with `mosquitto_pub` or HA and confirm it arrives whole.
- [ ] **Step 3: Record.** Fill in: `Spike results: bit_depth=__, loop timeout=__ s, fps=__, mem_free=__ bytes, ESP32 fw=__`. Pass: fps ≥ 8 and mem_free ≥ 20,000 with the bitmap and MQTT up. If fps < 8, stop and tell Philippe before going on.

Spike results: bit_depth=5, socket_timeout=0.05 s with loop(timeout=0.05) called at most every 200 ms (LOOP_EVERY_MS = 200), fps=31.7 drawing only / 22 with loop every frame at 0.01 s (lost 1 of 3 1,600-char messages, OSError 116) / 11.6 with loop every frame at 0.05 s (6 of 6 arrived), mem_free=78,000 to 100,000 bytes with MQTT up, ESP32 fw=1.2.2. Wi-Fi often needs one connect retry ("No such ssid" first try). MQTT user is `mqtt`.

### Task 3: `radar.py` core state (no drawing)

**Files:**
- Create: `circuitpython/radar.py`
- Test: `test/cp/test_radar.py` (run from repo root: `python3 -m unittest discover -s test/cp -t .`; tests add `circuitpython/` to `sys.path`)

**Interfaces:**
- Produces:
  - Constants from Global Constraints, plus `TICKS_PERIOD = 1 << 29`.
  - `elapsed(now: int, then: int) -> int` = `(now - then) % TICKS_PERIOD`.
  - `class Plane` with `id, route, type, x0, y0, hdg, spd, agl, x, y, d` (miles, degrees, knots, feet; same meaning as the C++ struct).
  - `class Radar`: attributes `range_mi: float`, `ring_mi: float`, `sweep_on: bool`, `planes: list[Plane]`, `ring: list[str]`, `idx: int`, `details_now: bool`, `have_data: bool`; methods
    - `parse(s: str, now: int) -> None`
    - `update(now: int) -> None` (stale check, positions, ring, rotate, quiet timer, `details_now`; the C++ `render` minus drawing)
    - `tap(up: int, now: int) -> dict | None` returns `{"range": v}` when on the radar screen, else `None`
    - `hold(up: int, now: int) -> dict | None` returns `{"ring": v}` when on the radar screen, else `None`
    - `toggle_sweep(now: int) -> dict` returns `{"sweep": bool}`, toast `SWEEP` / `ON` or `OFF`
    - `set_range(v: float)`, `set_ring(v: float)`, `set_sweep(on: bool)` for values from HA, no toast
    - `toast(now: int) -> tuple[str, str] | None` (active toast lines)
  - `snap_range(v) -> float` (nearest of 5, 10, 15, 20), `snap_ring(v) -> float` (clamp 0.5..3, round to 0.5), `fmt_mi(v) -> str`.

- [ ] **Step 1: Write failing tests.** Port the C++ scenarios with exact values:
  - `test_parse_basic`: parse `" UA1482,DEN>SFO,B738,-52,31,270,280,18500;N172SP,,C172,40,-20,315,100,1400"` → 2 planes; first `id "UA1482"`, `x0 -5.2`, `y0 3.1`, `hdg 270`, `spd 280`, `agl 18500`; second `route ""`.
  - `test_parse_skips_bad_records`: `"A,,,1,2,3,4,5;SHORT,1,2;B,,,x,2,3,4,5;C,,,1,2,3,4,-50"` → ids `["A", "C"]`, `C.agl == 0`. A non-numeric field skips that record (differs from C++ `atof`; on purpose).
  - `test_parse_empty_is_data`: `parse("", 0)` → `planes == []`, `have_data` True; after `update(1000)` not stale.
  - `test_coast`: plane `spd 100`, `hdg 90` at x0 0; `update(36_000)` → `x ≈ 1.15078 ± 0.001`; `update(120_000)` → `x ≈ 1.918 ± 0.001` (capped at 60 s).
  - `test_stale_clears`: data at 0, `update(120_001)` → planes empty, stale.
  - `test_ring_order_and_rotate`: the C++ "details 1" data at t=3000 → `ring == ["N172SP", "N4417K"]`, `details_now`; at t=9500 → `idx == 1`.
  - `test_tap_details_pauses`: tap(-1) in details → idx advances, no rotation for 30 s.
  - `test_hold_details_quiet`: hold in details → `details_now` False for 120 s, toast `("RADAR", "2 MIN")`.
  - `test_tap_radar_range`: range 10, `tap(+1)` → `{"range": 20}`, toast `("RANGE", "20 MI")`; `tap(+1)` again → `{"range": 20}`. From 15 (set by HA), `tap(-1)` → 10.
  - `test_hold_radar_ring`: ring 2, `hold(-1)` → `{"ring": 1}`, toast `("RING", "1 MI")`; ring 1.5 → `hold(+1)` → 2. `fmt_mi(1.5) == "1.5 MI"`.
  - `test_toggle_sweep`: on → `{"sweep": False}`, toast `("SWEEP", "OFF")`.
  - `test_snap`: `snap_range(7) == 5`, `snap_range(999) == 20`, `snap_ring(0.1) == 0.5`, `snap_ring(1.3) == 1.5`.
  - `test_tick_wrap`: parse at `TICKS_PERIOD - 1000`, `update(500)` → not stale, coasting used 1.5 s.
- [ ] **Step 2: Run, expect failures.** `python3 -m unittest discover -s test/cp -t .` → ImportError for `radar`.
- [ ] **Step 3: Implement** in `circuitpython/radar.py`, following `flight_radar.h` function by function (`parse`, `update_positions`, `update_ring` with 10% slack, `rotate`, `on_tap`, `on_hold`, `step_list`, `fmt_mi`). Timers become `(on, start)` pairs checked with `elapsed`.
- [ ] **Step 4: Run, expect pass.** Same command → all OK.

### Task 4: Font and drawing, matched against the C++ frames

**Files:**
- Create: `circuitpython/font.py`
- Modify: `circuitpython/radar.py` (add drawing)
- Create: `test/cp/fakes.py` (`FakeBitmap`), `test/cp/test_render.py`, `test/cp/golden_frames.txt`

**Interfaces:**
- Consumes: `Radar` from Task 3.
- Produces:
  - `font.GLYPHS: dict[str, str]` (copy of the C++ glyph table), `font.text_w(s) -> int`, `font.draw_text(bmp, x, y, s, c) -> None` (uppercases, unknown chars blank, 4 px per char).
  - Color indices in `radar.py`: `BLACK 0, HI_LOW 1, HI_MID 2, HI_HIGH 3, LO_LOW 4, LO_MID 5, LO_HIGH 6, WHITE 7, SOFT 8, GRAY 9, DIM 10, SWEEP 11, SWEEP_TAIL 12, BAR_OFF 13`; `COLORS: list[tuple[int, int, int]]` with the header's RGB values in that order.
  - `radar.palette_colors(brightness: int) -> list[int]` (0xRRGGBB per index, each channel scaled by brightness/255; a channel that is non-zero in `COLORS` stays ≥ 1).
  - `Radar.draw(bmp, now: int) -> None`: `bmp.fill(0)` then the radar or details screen. `bmp` supports `bmp[x, y] = c` and `bmp.fill(c)`.
  - `radar.lround(v: float) -> int`: rounds half away from zero, like C `lroundf`.

- [ ] **Step 1: Golden frames.** `g++ -std=c++17 -Wall -Wextra -I test/esphome_stub test/render_test.cpp -o /tmp/rt && /tmp/rt > test/cp/golden_frames.txt`. Check: 9 frames, "range now 20", "ring now 1".
- [ ] **Step 2: Write failing tests.** `FakeBitmap.to_rows()` maps each index's RGB through the stub's exact letter rule (`O`, `G`, `B`, `W`, `,`, `#`; `.` for 0). `test_render.py` replays the C++ scenario step for step (same `g_ms` values, same parse strings, `tap`/`hold` in place of `on_tap`/`on_hold`, range 10 and ring 2 set on the Radar) and asserts each frame equals the golden frame. Also:
  - `test_sweep_off`: sweep off → no `SWEEP` or `SWEEP_TAIL` pixels; otherwise equal to the sweep-on frame minus those pixels.
  - `test_palette`: `palette_colors(255)[HI_LOW] == 0xFF6E00`; `palette_colors(5)` has no zero channel where `COLORS` is non-zero; index 0 is `0`.
- [ ] **Step 3: Run, expect failures.**
- [ ] **Step 4: Implement.** Port `px`, `text`, `mark`, `alt_y`, `draw_right_message`, `draw_radar`, `draw_details` using `lround`. Cache the outer and inner ring pixel lists per (range, ring) so frames do no trig for them. Sweep drawn only when `sweep_on`.
- [ ] **Step 5: Run, expect pass.** If a frame differs by a single pixel from float32 vs float64 rounding, show the diff to the reviewer and justify it; any other difference is a bug.

### Task 5: `buttons.py`

**Files:**
- Create: `circuitpython/buttons.py`
- Test: `test/cp/test_buttons.py`

**Interfaces:**
- Produces: `class Buttons` with `update(up: bool, down: bool, now: int) -> tuple | None` (`True` = pressed), returning `("tap", 1)`, `("tap", -1)`, `("hold", 1)`, `("hold", -1)`, `("both",)` or `None`. Uses `radar.elapsed`.
- Rules: debounce 20 ms; event on release; tap = 20..600 ms; hold = 700..5000 ms; other lengths do nothing. Both down together for ≥ 100 ms → `("both",)` once, when the last one is released, and no single-button event for either in that press.

- [ ] **Step 1: Write failing tests** with a helper that feeds `(t, up, down)` samples every 10 ms: `test_tap_up` (0..200 ms) → `("tap", 1)` at release; `test_hold_down` (0..1000) → `("hold", -1)`; `test_gap_length_ignored` (650 ms) → nothing; `test_too_long` (6000) → nothing; `test_bounce` (one 10 ms glitch) → nothing; `test_both_release_order` (both 0..300, up released at 300, down at 450) → exactly one `("both",)`, at 450; `test_both_short_overlap` (up 0..200, down 150..200, overlap 50 ms) → handled as two separate presses by the normal rules; `test_wrap` (press across `TICKS_PERIOD`) → `("tap", 1)`.
- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect pass.**

### Task 6: `link.py`: MQTT topics, discovery, restore, reconnect

**Files:**
- Create: `circuitpython/link.py`
- Test: `test/cp/test_link.py`

**Interfaces:**
- Produces:
  - `NAMES = ("range", "ring", "brightness", "sweep")`, `state_topic(name) -> str`, `set_topic(name) -> str`, `PLANES = "flight_radar/planes"`, `STATUS = "flight_radar/status"`.
  - `discovery_messages() -> list[tuple[str, str]]`: retained config for three `number` entities and one `switch`, all under device `{"identifiers": ["flight_radar"], "name": "Flight Radar"}`, with `availability_topic` `STATUS`, `unique_id` `flight_radar_<name>`, names "Radar range", "Inner ring", "Brightness", "Sweep", the min/max/step/unit (`mi`) from Global Constraints, `mode: box` for numbers. Topics `homeassistant/number/flight_radar_<name>/config` and `homeassistant/switch/flight_radar_sweep/config`.
  - `decode(name, payload: str) -> float | int | bool | None`: range via `snap_range`, ring via `snap_ring`, brightness clamped 5..255 int, sweep `ON`/`OFF` (case-insensitive); `None` for garbage.
  - `encode(name, value) -> str`: `"10"`, `"1.5"`, `"128"`, `"ON"`.
  - `next_delay(attempt: int) -> int` = `min(60_000, 2_000 * 2 ** attempt)` ms.
  - `class Link(make_client, on_planes, on_setting, values: dict)`: `make_client() -> client` with MiniMQTT-like `connect()`, `loop(timeout)`, `publish(topic, msg, retain=False)`, `subscribe(topic)`, `unsubscribe(topic)`, `disconnect()`, attribute `on_message(client, topic, msg)`; the factory sets the last will (`STATUS`, `offline`, retained) and connects Wi-Fi. `values` holds current settings for republishing. Methods: `poll(now: int) -> None` (never raises), `publish_state(name, value) -> None` (never raises; updates `values`), `connected: bool`.
  - Restore: on the first successful connect, subscribe to the four state topics, the four set topics and `PLANES`; for `RESTORE_MS = 3000` accept state-topic messages as restored values (`on_setting(name, value)`), then unsubscribe state topics and publish all current values retained. On later reconnects skip restore: subscribe set topics and `PLANES`, publish all current values. Every connect publishes discovery and `online`.

- [ ] **Step 1: Write failing tests** with a `FakeClient` that records calls and can be told to raise:
  - `test_discovery`: 4 messages; range config has `"min": 5, "max": 20, "step": 5`, ring `0.5/3/0.5`, brightness `5/255/1`; all `availability_topic == "flight_radar/status"`; valid JSON.
  - `test_decode`: `decode("range", "7") == 5`, `decode("range", "abc") is None`, `decode("brightness", "999") == 255`, `decode("ring", "0") == 0.5`, `decode("sweep", "off") is False`, `decode("sweep", "maybe") is None`.
  - `test_restore_then_publish`: connect at 0, deliver `flight_radar/range/state` = `"20"` at 100 → `on_setting("range", 20)`; no state publishes before 3000; at 3000 publishes 4 retained states with current values and unsubscribes state topics.
  - `test_set_topic`: message on `flight_radar/ring/set` `"2.5"` → `on_setting("ring", 2.5)` and a retained publish of `"2.5"` to the state topic.
  - `test_planes`: message on `PLANES` → `on_planes(payload)`.
  - `test_drop_and_reconnect`: `loop` raises `OSError` at t=10_000 → `connected` False, no exception; no connect attempt before 12_000; failing connects back off 2, 4, 8 s; on reconnect, no restore window, states published at once.
  - `test_publish_while_down`: `publish_state` while disconnected → no raise, value published on next connect.
- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect pass.**

### Task 7: `code.py` glue and first run on the panel

**Files:**
- Create: `circuitpython/code.py`
- Delete: `circuitpython/spike.py`

**Interfaces:**
- Consumes: everything above; hardware setup and timing values from the Task 2 spike results.

- [ ] **Step 1: Write `code.py`.** Matrix, bitmap, `TileGrid`, `Palette` from `palette_colors(brightness)`; buttons on `board.BUTTON_UP`/`BUTTON_DOWN` with `Pull.UP`, pressed = `not value`; `Radar`, `Buttons`, `Link` with a factory around `adafruit_esp32spi` + MiniMQTT using `os.getenv` settings and the spike's timeout. `on_setting` routes range/ring/sweep to `Radar.set_*` and brightness to the palette. Button events call `tap`/`hold`/`toggle_sweep` and pass any returned dict to `link.publish_state`. Loop: `link.poll(now)`, buttons, `radar.update(now)`, `radar.draw(bmp, now)`, `display.refresh()`. Network setup must not block the first frames: the radar shows NO DATA while connecting.
- [ ] **Step 2: Copy to the board.** `cp circuitpython/{code,radar,font,buttons,link}.py /Volumes/CIRCUITPY/`. Check serial output for errors.
- [ ] **Step 3: Check on the panel with Philippe.** NO DATA before data; radar after `mosquitto_pub -r -t flight_radar/planes -m "<packed from the C++ scenario>"`; details when a plane is in the ring; each button gesture from the README table plus Up+Down; entities appear in HA; changing range in HA changes the panel within a second; unplug and replug: settings come back. Record fps and `gc.mem_free()` from serial.

### Task 8: HA package: publish planes, drop dimming

**Files:**
- Modify: `homeassistant/flight_radar.yaml` (replace the `automation:` block)
- Modify: `test/template_test.py`

- [ ] **Step 1: Write failing test.** In `template_test.py`, assert: one automation, id `flight_radar_publish`; triggers include a `state` trigger on `sensor.flight_radar_planes` attribute `packed`, a `homeassistant` `start` trigger, and a `time_pattern` trigger `seconds: "/30"` (empty-sky heartbeat); one action `mqtt.publish` with `topic: flight_radar/planes`, `retain: true`, and a payload template that renders to the packed string with the test's Jinja env and to `""` when the attribute is missing; no `number.set_value` anywhere in the file.
- [ ] **Step 2: Run, expect failure.** `uv run --with pyyaml --with jinja2 python3 test/template_test.py`.
- [ ] **Step 3: Replace the dimming automation** with the publish automation. Payload: `{{ state_attr('sensor.flight_radar_planes', 'packed') or '' }}`.
- [ ] **Step 4: Run, expect pass.** The existing packed output is unchanged.

### Task 9: Docs

**Files:**
- Modify: `README.md`, `CLAUDE.md`

- [ ] **Step 1: README.** Hardware line says Matrix Portal M4. Setup: steps 1 to 6 unchanged; new steps for the CircuitPython upgrade (double-tap RESET, copy UF2), `circup` libraries, copying `circuitpython/*.py`, `settings.toml` keys, MQTT entities appearing under "Flight Radar". Buttons table gains "Up + Down together: sweep on/off". Entities paragraph lists the range, ring, brightness and sweep entity ids as HA shows them after Task 7, and drops the dimming sentence. Tuning points at `circuitpython/radar.py`. Short note: `esphome/` is for a Matrix Portal S3. Status reflects what Task 7 checked.
- [ ] **Step 2: CLAUDE.md.** Files list, data path (MQTT topics), sweep toggle in Design decisions, Testing commands (`python3 -m unittest discover -s test/cp -t .`, golden frames regen, template test via `uv run`), Status and Next steps.
- [ ] **Step 3: Check.** `grep -n -i -E "sunset|esphome run" README.md` returns only the S3 note. `grep -n "—" README.md CLAUDE.md` returns nothing.
