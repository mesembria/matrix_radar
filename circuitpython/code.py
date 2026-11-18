# Flight radar on a 64x32 HUB75 panel with an Adafruit Matrix Portal M4.
# Glue between the board and the logic in radar.py, buttons.py and link.py.
# Settings (Wi-Fi, MQTT broker) come from settings.toml.

import gc
import os

import board
import busio
import digitalio
import displayio
import framebufferio
import rgbmatrix
import supervisor

import adafruit_connection_manager
import adafruit_minimqtt.adafruit_minimqtt as MQTT
from adafruit_esp32spi import adafruit_esp32spi

import link
from buttons import Buttons
from link import Link
from radar import COLORS, Radar, elapsed, palette_colors

# ---------- Panel ----------
displayio.release_displays()
matrix = rgbmatrix.RGBMatrix(
    width=64, height=32, bit_depth=5,
    rgb_pins=[board.MTX_R1, board.MTX_G1, board.MTX_B1, board.MTX_R2, board.MTX_G2, board.MTX_B2],
    addr_pins=[board.MTX_ADDRA, board.MTX_ADDRB, board.MTX_ADDRC, board.MTX_ADDRD],
    clock_pin=board.MTX_CLK, latch_pin=board.MTX_LAT, output_enable_pin=board.MTX_OE)
display = framebufferio.FramebufferDisplay(matrix, auto_refresh=False)
bmp = displayio.Bitmap(64, 32, len(COLORS))
palette = displayio.Palette(len(COLORS))
group = displayio.Group()
group.append(displayio.TileGrid(bmp, pixel_shader=palette))
display.root_group = group


def set_brightness(b):
    for i, c in enumerate(palette_colors(b)):
        palette[i] = c


# ---------- Buttons (active low, no pull-ups on the board) ----------
def button(pin):
    b = digitalio.DigitalInOut(pin)
    b.switch_to_input(pull=digitalio.Pull.UP)
    return b


btn_up, btn_down = button(board.BUTTON_UP), button(board.BUTTON_DOWN)

# ---------- State ----------
values = {"range": 10, "ring": 2, "brightness": 128, "sweep": True}
radar = Radar()
buttons = Buttons()
set_brightness(values["brightness"])


def on_planes(msg):
    radar.parse(msg, supervisor.ticks_ms())


def on_setting(name, v):
    if name == "range":
        radar.set_range(v)
    elif name == "ring":
        radar.set_ring(v)
    elif name == "sweep":
        radar.set_sweep(v)
    elif name == "brightness":
        set_brightness(v)


# ---------- Network ----------
esp = adafruit_esp32spi.ESP_SPIcontrol(
    busio.SPI(board.SCK, board.MOSI, board.MISO),
    digitalio.DigitalInOut(board.ESP_CS), digitalio.DigitalInOut(board.ESP_BUSY),
    digitalio.DigitalInOut(board.ESP_RESET))
pool = adafruit_connection_manager.get_radio_socketpool(esp)


# Called by Link for every connect attempt. Raises on failure; Link retries with backoff.
def make_client():
    try:  # free the old client's socket after a drop
        adafruit_connection_manager.connection_manager_close_all(pool)
    except RuntimeError:
        pass  # nothing opened yet
    if not esp.is_connected:
        esp.connect_AP(os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD"))
    c = MQTT.MQTT(broker=os.getenv("MQTT_BROKER"), port=int(os.getenv("MQTT_PORT", 1883)),
                  username=os.getenv("MQTT_USER"), password=os.getenv("MQTT_PASSWORD"),
                  client_id="flight-radar", socket_pool=pool,
                  socket_timeout=link.LOOP_TIMEOUT, recv_timeout=5, keep_alive=60)
    c.will_set(link.STATUS, "offline", retain=True)
    return c


net = Link(make_client, on_planes, on_setting, values)

# ---------- Main loop ----------
frames, stats_ms = 0, supervisor.ticks_ms()
while True:
    now = supervisor.ticks_ms()
    frames += 1
    if elapsed(now, stats_ms) >= 60000:  # health line on the USB console
        print("fps %.1f  free %d  planes %d" % (frames * 1000 / elapsed(now, stats_ms), gc.mem_free(), len(radar.planes)))
        frames, stats_ms = 0, now
    ev = buttons.update(not btn_up.value, not btn_down.value, now)
    if ev:
        if ev[0] == "both":
            changed = radar.toggle_sweep(now)
        elif ev[0] == "tap":
            changed = radar.tap(ev[1], now)
        else:
            changed = radar.hold(ev[1], now)
        for name, v in (changed or {}).items():
            net.publish_state(name, v)
    radar.update(now)
    radar.draw(bmp, now)
    display.refresh(minimum_frames_per_second=0)
    # Free this frame's scraps first: big plane messages need one 2+ KB block,
    # and without this the heap fragments until they fail (seen with 40 planes).
    gc.collect()
    net.poll(supervisor.ticks_ms())
