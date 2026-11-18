# Flight radar on the Matrix Portal M4: design

## Why
The firmware in `esphome/` targets the Matrix Portal S3. Philippe owns a Matrix Portal M4 (SAMD51 main chip, ESP32 only as a Wi-Fi co-processor), which ESPHome can't run on. Rather than buy an S3, port the radar to CircuitPython on the M4.

## Goals
- Same screens, colors, marks, timings and button behavior as today. CLAUDE.md "Design decisions" and `esphome/flight_radar.h` are the reference.
- Range, inner ring and brightness show up in Home Assistant as number entities that HA can change and the buttons can change, both ways.
- Settings survive a reboot.
- The radar sweep can be turned off and on (Philippe's request: it may get old).

## Non-goals
- Night dimming. Drop the sunset/sunrise automation (Philippe's call).
- Deleting `esphome/`. It stays as is, for a future S3 (builder's call: costs nothing to keep).
- New features beyond what the ESPHome version does.

## Anti-goals
- A radar that stutters or freezes for seconds at a time. Short pauses when a message arrives are fine.
- A board that needs a manual reset after Wi-Fi or the broker drops.

## Constraints
- Hardware: Matrix Portal M4, 64x32 HUB75 panel, Up/Down buttons (`board.BUTTON_UP`, `board.BUTTON_DOWN`, active low).
- CircuitPython on the board is 7.3.1 (2022). Upgrade to the current stable release and matching library bundle.
- No hardware brightness on the M4's `rgbmatrix`. Brightness = scaling palette colors. Coarse at the low end; accepted.
- HA runs Mosquitto and the MQTT integration already.
- The board currently holds a weather display project. Copy the whole `CIRCUITPY` drive into `backup/weather-display/` before touching it.
- Writing style for any user-facing text: plain short words, active voice, no em dashes.

## Approaches
- **A. HA helpers + REST polling.** `input_number` helpers, board polls one sensor every 20 s, buttons POST back. No new services, but HA changes lag up to 20 s and each poll freezes the radar.
- **B. MQTT for settings only.** Number entities via MQTT discovery; planes still over REST. Two connections and an HA token.
- **B+. All MQTT (picked).** Planes and settings both over MQTT. One connection, no HA token, no polling, changes apply at once both ways. Costs: reconnect logic on the board, one extra automation in the HA package. Picked because MQTT is already running in HA, which removed B's main cost.

## How it works (decided)

### Data path
- The HA template sensor `sensor.flight_radar_planes` and its `packed` format stay exactly as they are.
- A new automation in `homeassistant/flight_radar.yaml` publishes `packed` to `flight_radar/planes` (retained, QoS 0) whenever the attribute changes, and once at HA start.
- The board subscribes to `flight_radar/planes`. Each message replaces the plane list, same as `fr::parse` today. Between messages, dots coast along heading at speed, as today (stop after 60 s; NO DATA after 2 min without a message).

### Settings
- The board announces three `number` entities via MQTT discovery under device "Flight Radar": Radar range (5/10/20 mi, step 5), Inner ring (0.5 to 3 mi, step 0.5, buttons step 1/2/3), Brightness (5 to 255).
- Topics: `flight_radar/<setting>/state` (board publishes, retained) and `flight_radar/<setting>/set` (HA publishes).
- A fourth entity, a `switch` named Sweep (default on), turns the sweep line on and off. Same topics pattern: `flight_radar/sweep/state` and `/set`, payloads `ON`/`OFF`.
- Button gesture for the sweep: press Up and Down together (either screen), act on release of both. Shows a short toast ("SWEEP ON"/"SWEEP OFF") like the other setting changes. A press counts as "together" when both are down at the same time for at least 100 ms; that press does not also count as a tap or hold of either button (builder's call on the gesture, Philippe can change it).
- On boot the board reads the retained state topics to restore values, falling back to 10 mi / 2 mi / 128.
- A button change updates the screen at once, then publishes the new state.
- Availability: last will `flight_radar/status` = `offline`, `online` after connect.

### Board software
- `circuitpython/` folder in the repo, mirrored onto `CIRCUITPY`:
  - `code.py`: main loop (MQTT poll, buttons, frame timing).
  - `radar.py`: pure logic and drawing (parse, coasting, bands, rotation, button actions, every screen) drawing into a 64x32 indexed bitmap. No hardware imports, so it runs under desktop Python.
  - `font.py`: the 3x5 font from the header.
  - `settings.toml.example`: Wi-Fi SSID/password, broker host, port, user, password. The real `settings.toml` lives only on the board.
- Wi-Fi and MQTT via `adafruit_esp32spi` + `adafruit_minimqtt`. Non-blocking-ish loop: `mqtt.loop(timeout)` with a short timeout each frame. On any network error, keep drawing and retry with backoff.

### Testing
- Desktop render test like `test/render_test.cpp`: run `radar.py` under CPython, print ASCII frames of every screen with the same letter legend, and compare by eye with the C++ output.
- HA side: extend `test/template_test.py` only if the template changes (it shouldn't).
- On the board: measure frame rate and free memory (`gc.mem_free()`) early, before building every screen.

### Docs
- README: new setup for the M4 (CircuitPython upgrade, copy files, `settings.toml`, MQTT), remove ESPHome and dimming steps from the main path (keep a short note that `esphome/` is for an S3). CLAUDE.md: update files, status, next steps.

## Left to the builder
- Frame rate target (aim for at least 8 fps with the sweep on; drop the sweep rate before dropping marks if slow).
- Drawing strategy for speed (static layer drawn once vs full redraw).
- Exact backoff timings, discovery payload details, MQTT client id.
- How brightness maps to palette scaling.
