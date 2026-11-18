# Flight radar matrix: handoff

A 64x32 HUB75 LED panel (Adafruit, 4 mm pitch) on an Adafruit Matrix Portal M4 (SAMD51 plus an ESP32 Wi-Fi co-processor) shows a live radar of planes around Philippe's house in Lafayette, CO. When a plane enters the inner ring, the panel switches to that plane's details. The panel goes in his home office. Home Assistant runs on a Raspberry Pi 4 (`homeassistant.local`, 192.168.1.177) with the Mosquitto add-on.

The board runs CircuitPython, not ESPHome: the M4's main chip isn't an ESP32. `esphome/` is the earlier S3 version, kept as the reference the CircuitPython port was matched against. Design and plan: `docs/superpowers/specs/2026-10-29-matrix-portal-m4-port-design.md`, `docs/superpowers/plans/2026-10-29-matrix-portal-m4-port.md`.

README.md is the user-facing setup and usage guide. Keep it in sync with any behavior change.

## Files
- `homeassistant/flight_radar.yaml`: HA package. Template sensor `sensor.flight_radar_planes` builds a `packed` attribute from the Flightradar24 integration (`sensor.flightradar24_current_in_area`). Automation `flight_radar_publish` sends it to MQTT.
- `circuitpython/`: the board's code (copied onto `CIRCUITPY`).
  - `code.py`: hardware glue (panel, buttons, ESP32 + MiniMQTT) and the main loop.
  - `radar.py`: data parsing, plane movement, ring/rotation, button actions, all drawing. No board imports.
  - `font.py`: the 3x5 font. `buttons.py`: tap/hold/both detection. `link.py`: MQTT topics, discovery, restore, reconnect.
  - `settings.toml.example`: Wi-Fi and broker keys. The real `settings.toml` lives only on the board.
- `esphome/`: the S3 version (`flight-radar.yaml`, `flight_radar.h`). Compiles; never flashed.
- `backup/weather-display/`: what was on the board before (a weather display project).
- `test/`: offline checks (see Testing).

## Data path
HA publishes `packed` to `flight_radar/planes` (retained) on change and every 30 s (an empty sky never changes state). The board announces three MQTT `number`s and one `switch` under device "Flight Radar": topics `flight_radar/<range|ring|brightness|sweep>/state` (board publishes, retained) and `/set` (HA publishes). On its first connect after boot the board reads the retained states for 3 s, then publishes its own. Last will: `flight_radar/status` = `offline`.

## Data format
`packed` = `id,route,type,x,y,heading,speed,agl,model;...`, closest first, max 40 planes. `model` = the integration's `aircraft_model`, upper case, `A-Z 0-9 - space`, cut to 16 characters; the board also accepts 8-field records.
x/y = tenths of a mile east/north of home; heading in degrees; speed in knots; agl = feet above the house (`ground_ft` = 5240, rough, the user should set the real value). Planes on the ground are skipped. id = flight number, else registration, else callsign, stripped to A-Z0-9. Route = `DEN>SFO` or empty. The board skips a record with a non-numeric field.

## Design decisions (agreed with the user, keep them)
- Radar on the left (center 15,16, radius 14 px). Range number top left. Defaults: 10 mi range, 2 mi ring.
- Colors: radar, sweep, home dot and all text in a cool green (the user liked the green test screen); planes keep orange/green/blue. The original whites and grays are in `test/cp/test_render.py` as `REFERENCE_COLORS`.
- Height bands above ground: <3,000 ft orange plus sign; 3,000 to 10,000 ft green dot with tail; >10,000 ft blue single dot. Shape and color both carry the band. Tails point where the plane came from.
- Altitude scale runs up the panel's right edge (x=63), ground at the bottom, a 3-px tick per plane at x=60..62, per-band count and marker to the left. No clock and no word labels (the user asked for both).
- Sweep reveals planes (user's request): a mark is drawn where the sweep last crossed it, fading 100/70/50/33% until the next pass. Turn = 10 s at 5 mi, 20 s at 10/20 mi (small planes, ~110 kt, move about a pixel per turn; capped at the 20 s data rate). Crossing = the plane's "angle ahead of the sweep" wraps, so planes moving against the sweep can't slip past. Sweep off: live, full brightness.
- Details page (user's design): left = ID + n/N, route or speed, height; right = mini radar (center 53,10, radius 9, edge = ring x 1.1) with the plane as dot + tail; full-width plane type name (falls back to the code); bottom bar = closeness (full overhead, empty at the ring). No distance line, no rotation countdown (n/N is enough).
- Several planes in the ring: rotate every 6 s in arrival order.
- Buttons, `board.BUTTON_UP` and `board.BUTTON_DOWN`, active low, internal pull-ups, act on release:
  - Radar: tap = zoom 5/10/20 mi (Up = out); hold ~1 s = inner ring 1/2/3 mi (Up = bigger).
  - Details: tap = previous/next plane (Up = previous), pauses rotation 30 s (bar turns gray); hold = radar only for 2 min (pause symbol bottom left).
  - Up and Down together (100 ms or more), either screen: sweep on/off. The user asked for a sweep toggle; the gesture was Claude's call.
- Range, ring, brightness and sweep are MQTT entities so HA can change them too. No night dimming (the user dropped it).
- Brightness scales palette colors (no hardware brightness on the M4); lit channels never drop to 0.
- NO DATA on the right after 2 min without updates. Dots stop moving 60 s after the last update.
- Tiny custom 3x5 font so the look matches the mockups; no font files.
- User's writing preferences for any text: plain short words, active voice, no em dashes, concise.

## Board notes
- CircuitPython 10.3.1, libraries via `circup`. ESP32 firmware is old (1.2.2) but works.
- Timing uses `supervisor.ticks_ms()` (wraps every ~6.2 days); every difference goes through `radar.elapsed()`.
- `code.py` runs `gc.collect()` every frame: without it, 2.3 KB plane messages failed with MemoryError while 50 KB was free (fragmentation).
- MQTT `loop()` blocks for its timeout, so `link.py` calls it at most every 200 ms with 0.05 s. 0.01 s lost large messages (spike results in the plan).
- Wi-Fi often fails the first join ("No such ssid"); Link retries with backoff (2, 4, 8 ... 60 s).
- Use the broker's IP in `settings.toml`; the ESP32 can't resolve `.local` names.
- The console (USB serial, 115200) prints MQTT status and a once-a-minute "fps / free / planes" line.

## Status
- Done: board on CircuitPython 10.3.1 running the green radar, sweep reveal + fade, and the new details page. Live data flows from HA (Flightradar24 integration installed, package in `config/packages/`). 58 desktop tests pass. 40-plane messages handled (with the per-frame `gc.collect()`), about 14 fps.
- Not done: Philippe pastes the package with the `model` field; check the new details page with real planes.

## Next steps
1. User: `pbcopy < homeassistant/flight_radar.yaml`, paste over `config/packages/flight_radar.yaml` in HA's File editor, then Developer tools > YAML > reload Template entities and Automations.
2. Check on the panel: names on the details page, mini radar, closeness bar, fade strength, readability across the room.
3. Still unchecked from the first round: every button gesture, HA entity changes both ways, unplug/replug keeps settings.

## Testing
- Board logic and drawing: `python3 -W error -m unittest discover -s test/cp`.
  `test_render.py` compares every screen with the snapshot `test/cp/golden_frames.txt` (scenario in `test/cp/scenario.py`). After a deliberate change to the screens, run `python3 test/cp/make_golden.py`, look at the frames, and keep them.
  In the frames, O = orange, G = green, B = blue, W = white, # = other lit, , = dim. The screens matched the C++ version pixel for pixel until the sweep and details redesign; the C++ render test still runs on its own.
- HA template and automation: `uv run --with pyyaml --with jinja2 python3 test/template_test.py`.
- ESPHome config check (S3 version): `esphome config esphome/flight-radar.yaml`.
