# Flight radar matrix

A 64x32 LED panel (Adafruit, 4 mm pitch) on an Adafruit Matrix Portal M4 that shows a live radar of planes around the house. When a plane crosses the inner ring, the panel switches to that plane's details.

## Files

| File | Goes in |
|---|---|
| `homeassistant/flight_radar.yaml` | Home Assistant `config/packages/` |
| `circuitpython/code.py`, `radar.py`, `font.py`, `buttons.py`, `link.py` | the board's `CIRCUITPY` drive |
| `circuitpython/settings.toml.example` | the board's `CIRCUITPY` drive, as `settings.toml` |

`esphome/` holds an older version for the Matrix Portal S3. The M4 can't run it.

## Setup

1. **Install the Flightradar24 integration** from HACS (AlexandrErohin/home-assistant-flightradar24) and restart Home Assistant.
2. **Add it** in Settings > Devices & services. Use your home coordinates and a radius of 20 miles (32 km, in whatever unit the form asks for). Set the scan interval to 20 seconds. Leave the altitude filters empty.
3. **Turn on packages** if you haven't already. In `configuration.yaml`:
   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```
4. **Copy `flight_radar.yaml`** into `config/packages/`. Set `ground_ft` near the top of the template to your house's elevation (it's 5240 now, roughly Lafayette). Restart.
5. **Check the sensor.** In Developer tools > States, `sensor.flight_radar_planes` should show a count, and its `packed` attribute should hold a string like `N172SP,,C172,10,-5,315,100,1400,CESSNA 172S SKYH;...`.
6. **Keep it out of the history database.** The attribute changes every 20 seconds. In `configuration.yaml`:
   ```yaml
   recorder:
     exclude:
       entities:
         - sensor.flight_radar_planes
   ```
7. **Set up MQTT** if you haven't: the Mosquitto broker add-on and the MQTT integration. Make a Home Assistant user for the board (Settings > People > Users). Mosquitto accepts its username and password.
8. **Update CircuitPython.** Plug the board into your computer over USB-C and double-tap RESET (the button next to the USB-C port). A `MATRIXBOOT` drive shows up. Copy the latest CircuitPython UF2 for the Matrix Portal M4 from circuitpython.org onto it. The board restarts as a `CIRCUITPY` drive.
9. **Install the libraries:** `pip install circup`, then `circup install adafruit_esp32spi adafruit_minimqtt adafruit_connection_manager`.
10. **Copy the files** from `circuitpython/` onto `CIRCUITPY`. Copy `settings.toml.example` as `settings.toml` and fill in your Wi-Fi, the broker's IP address (use the IP, not `homeassistant.local`), and the MQTT user from step 7.
11. **Check it.** A "Flight Radar" device shows up under the MQTT integration. If the panel says NO DATA after a minute, check that the sensor in step 5 has a `packed` attribute and that the automation "Flight radar: send planes to the panel" is on. To see what the board is doing, open its USB serial console (115200 baud): it prints MQTT status and, once a minute, frame rate and free memory.
12. **Power.** Use a 5 V USB-C supply rated for at least 3 A. The screen is mostly dark, but a laptop port can still fall short.

## How to use it

**Radar (idle screen)**
- Left: the radar, drawn in green. Your house is the bright dot in the middle. The faint ring is the inner ring.
- Top left: range in miles.
- Right: an altitude scale with ground at the bottom. Every plane gets a tick at its height. The number beside each section counts the planes in it.
- Plane marks (height above your house, not above sea level):

  | Height | Mark | Color |
  |---|---|---|
  | Under 3,000 ft | plus sign with tail | orange |
  | 3,000 to 10,000 ft | dot with tail | green |
  | Over 10,000 ft | single dot | blue |

  The tail points where the plane came from.
- The sweep reveals the planes, like a real radar. A plane shows up when the sweep first reaches it, and only moves when the sweep passes it again. Between passes it slowly fades. One turn takes 10 seconds at 5 mi and 20 seconds at 10 and 20 mi, about the time a small plane needs to move one dot. With the sweep off, planes stay bright and move all the time.
- A pause symbol (two bars) in the bottom left means details are snoozed.
- NO DATA on the right means nothing has come from Home Assistant for 2 minutes.

**Details (a plane is inside the inner ring)**
- Left: flight number (airlines) or registration (small planes), plus "1/3" when several are inside. Below it, the route (DEN>SFO) or ground speed for planes with no route, then the height above ground in the height color.
- Right: a small radar. Your house is in the middle, the edge is the inner ring, and the plane is a dot with a tail showing where it came from.
- Full width: the type of plane ("CESSNA 172S SKYH", "BOEING 737-8H4"), or its short code if Flightradar24 has no name for it.
- Bottom bar: how close the plane is. Full means right over the house; empty means at the edge of the inner ring.

With several planes inside, they rotate every 6 seconds in the order they arrived.

**Buttons (on the board's edge)**

| | Radar | Details |
|---|---|---|
| Tap Up | zoom out (5, 10, 20 mi) | previous plane |
| Tap Down | zoom in | next plane |
| Hold Up (about 1 s, then let go) | bigger inner ring (1, 2, 3 mi) | radar only for 2 minutes |
| Hold Down | smaller inner ring | radar only for 2 minutes |
| Press Up and Down together | sweep on or off | sweep on or off |

A tap in details pauses rotation for 30 seconds (the bar turns gray).

Range, inner ring, brightness and sweep also appear in Home Assistant under the "Flight Radar" device (`number.flight_radar_radar_range`, `number.flight_radar_inner_ring`, `number.flight_radar_brightness`, `switch.flight_radar_sweep`). Changes go both ways right away. The broker stores them, so they survive a restart. Brightness works by dimming the colors, so very low values look a bit coarse.

## Tuning

All in `circuitpython/radar.py`, at the top:
- `LOW_FT`, `MID_FT`: height cutoffs (3,000 and 10,000)
- `ROTATE_MS`, `PAUSE_MS`, `QUIET_MS`: rotation pace, pause after a tap, snooze length
- `RANGES`, `RINGS`: the steps the buttons move through

In the Home Assistant package: `ground_ft` and `max_planes` (40).

## How it works

Home Assistant turns the Flightradar24 data into one short string with each plane's position (miles east and north of the house), heading, speed and height. An automation in the package publishes it to the MQTT topic `flight_radar/planes` when it changes, and every 30 seconds in any case. The board listens on that topic. Between updates, the board moves each plane along its heading at its speed, and the sweep shows where it is now each time it passes. Each update then corrects the positions. If updates stop, the planes stop moving after a minute.

## Status

- Runs on the Matrix Portal M4 with CircuitPython 10.3.1. Connects to MQTT and shows up in Home Assistant.
- Every screen matches the original drawing pixel for pixel in the desktop tests (`test/cp/`).
- Not yet checked on the real panel with live flights.
