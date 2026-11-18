#pragma once
// Flight radar for a 64x32 HUB75 panel on an Adafruit Matrix Portal S3.
// Included by flight-radar.yaml. All drawing and button logic lives here.
//
// Data comes from Home Assistant as one string:
//   "id,route,type,x,y,heading,speed,agl;id,route,..."
//   x, y    = tenths of a mile east / north of home
//   heading = degrees, speed = knots, agl = feet above ground

#include "esphome.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

namespace fr {

using esphome::Color;
using esphome::display::Display;
using esphome::number::Number;

// ---------- Settings you might want to change ----------
constexpr int LOW_FT = 3000;        // under this: low (orange plus sign)
constexpr int MID_FT = 10000;       // under this: mid (green dot with tail)
constexpr int TOP_FT = 40000;       // top of the altitude scale
constexpr uint32_t ROTATE_MS = 6000;   // time per plane when several are in the ring
constexpr uint32_t PAUSE_MS = 30000;   // rotation pause after a button tap
constexpr uint32_t QUIET_MS = 120000;  // radar-only time after a long press
constexpr uint32_t TOAST_MS = 1800;    // how long setting messages stay up
constexpr uint32_t STALE_MS = 120000;  // no data for this long = "NO DATA"
constexpr uint32_t SWEEP_MS = 4000;    // one sweep turn
constexpr float MAX_COAST_S = 60.0f;   // stop moving dots this long after the last update
constexpr float RANGES[] = {5, 10, 20};
constexpr float RINGS[] = {1, 2, 3};

// ---------- Colors ----------
inline Color band_hi(int b) {
  switch (b) {
    case 0: return Color(255, 110, 0);   // low: orange
    case 1: return Color(70, 210, 40);   // mid: green
    default: return Color(40, 100, 255); // high: blue
  }
}
inline Color band_lo(int b) {
  switch (b) {
    case 0: return Color(80, 32, 0);
    case 1: return Color(16, 60, 10);
    default: return Color(10, 26, 80);
  }
}
inline Color c_white() { return Color(230, 230, 225); }
inline Color c_soft() { return Color(170, 165, 150); }
inline Color c_gray() { return Color(110, 108, 100); }
inline Color c_dim() { return Color(40, 40, 38); }
inline Color c_sweep() { return Color(0, 70, 50); }
inline Color c_sweep_tail() { return Color(0, 28, 20); }
inline Color c_bar_off() { return Color(35, 35, 35); }

inline int band(int agl) { return agl < LOW_FT ? 0 : (agl < MID_FT ? 1 : 2); }

// ---------- State ----------
struct Plane {
  std::string id, route, type;
  float x0 = 0, y0 = 0;  // miles east / north of home when the data arrived
  int hdg = 0, spd = 0, agl = 0;
  float x = 0, y = 0, d = 0;  // current estimate
};

inline std::vector<Plane> planes;
inline bool have_data = false;
inline uint32_t data_ms = 0;

inline std::vector<std::string> ring;  // ids inside the inner ring, in arrival order
inline size_t idx = 0;
inline uint32_t shown_ms = 0;
inline bool details_now = false;

inline bool pause_on = false, quiet_on = false, toast_on = false;
inline uint32_t pause_ms = 0, quiet_ms = 0, toast_ms = 0;
inline std::string toast1, toast2;

inline uint32_t now() { return esphome::millis(); }

// True while a timer is running; switches itself off when it runs out.
inline bool running(bool &on, uint32_t start, uint32_t dur) {
  if (on && now() - start >= dur) on = false;
  return on;
}

// ---------- Tiny 3x5 font ----------
inline const char *glyph(char c) {
  switch (c) {
    case 'A': return "010101111101101"; case 'B': return "110101110101110";
    case 'C': return "011100100100011"; case 'D': return "110101101101110";
    case 'E': return "111100110100111"; case 'F': return "111100110100100";
    case 'G': return "011100101101011"; case 'H': return "101101111101101";
    case 'I': return "111010010010111"; case 'J': return "001001001101010";
    case 'K': return "101101110101101"; case 'L': return "100100100100111";
    case 'M': return "101111111101101"; case 'N': return "110101101101101";
    case 'O': return "010101101101010"; case 'P': return "110101110100100";
    case 'Q': return "010101101110011"; case 'R': return "110101110101101";
    case 'S': return "011100010001110"; case 'T': return "111010010010010";
    case 'U': return "101101101101111"; case 'V': return "101101101101010";
    case 'W': return "101101111111101"; case 'X': return "101101010101101";
    case 'Y': return "101101010010010"; case 'Z': return "111001010100111";
    case '0': return "111101101101111"; case '1': return "010110010010111";
    case '2': return "110001010100111"; case '3': return "110001010001110";
    case '4': return "101101111001001"; case '5': return "111100110001110";
    case '6': return "011100111101111"; case '7': return "111001010010010";
    case '8': return "111101111101111"; case '9': return "111101111001110";
    case '>': return "100010001010100"; case ':': return "000010000010000";
    case '.': return "000000000000010"; case '/': return "001001010100100";
    case '?': return "110001010000010";
    default: return nullptr;  // space and anything unknown draw as blank
  }
}

inline void px(Display &it, float x, float y, Color c) {
  int ix = (int) lroundf(x), iy = (int) lroundf(y);
  if (ix < 0 || ix >= 64 || iy < 0 || iy >= 32) return;
  it.draw_pixel_at(ix, iy, c);
}

inline int text_w(const std::string &s) { return s.empty() ? 0 : (int) s.size() * 4 - 1; }

inline void text(Display &it, int x, int y, const std::string &s, Color c) {
  for (char ch : s) {
    const char *g = glyph((char) toupper((unsigned char) ch));
    if (g)
      for (int r = 0; r < 5; r++)
        for (int q = 0; q < 3; q++)
          if (g[r * 3 + q] == '1') px(it, x + q, y + r, c);
    x += 4;
  }
}

inline float rad(float deg) { return deg * (float) M_PI / 180.0f; }

// Plane marker. Shape and color both say the height band.
inline void mark(Display &it, float X, float Y, int b, int hdg) {
  float h = rad(hdg);
  Color hi = band_hi(b), lo = band_lo(b);
  if (b == 0) {  // low: plus sign with a tail
    px(it, X - sinf(h) * 2.2f, Y + cosf(h) * 2.2f, lo);
    px(it, X, Y, hi); px(it, X - 1, Y, hi); px(it, X + 1, Y, hi);
    px(it, X, Y - 1, hi); px(it, X, Y + 1, hi);
  } else if (b == 1) {  // mid: dot with a tail
    px(it, X - sinf(h) * 1.4f, Y + cosf(h) * 1.4f, lo);
    px(it, X, Y, hi);
  } else {  // high: single dot
    px(it, X, Y, hi);
  }
}

inline std::string fmt_mi(float v) {
  char b[16];
  if (fabsf(v - roundf(v)) < 0.05f) snprintf(b, sizeof b, "%d MI", (int) roundf(v));
  else snprintf(b, sizeof b, "%.1f MI", v);
  return b;
}

// ---------- Data in ----------
inline std::string trim(const std::string &s) {
  size_t a = s.find_first_not_of(" \t\r\n"), b = s.find_last_not_of(" \t\r\n");
  return a == std::string::npos ? "" : s.substr(a, b - a + 1);
}

inline void parse(const std::string &s) {
  std::vector<Plane> out;
  size_t start = 0;
  while (start < s.size()) {
    size_t end = s.find(';', start);
    if (end == std::string::npos) end = s.size();
    std::string rec = trim(s.substr(start, end - start));
    start = end + 1;
    if (rec.empty()) continue;
    std::vector<std::string> f;
    size_t a = 0;
    while (true) {
      size_t b = rec.find(',', a);
      f.push_back(trim(rec.substr(a, b == std::string::npos ? std::string::npos : b - a)));
      if (b == std::string::npos) break;
      a = b + 1;
    }
    if (f.size() < 8) continue;
    Plane p;
    p.id = f[0].empty() ? "?" : f[0];
    p.route = f[1];
    p.type = f[2];
    p.x0 = atof(f[3].c_str()) / 10.0f;
    p.y0 = atof(f[4].c_str()) / 10.0f;
    p.hdg = atoi(f[5].c_str());
    p.spd = atoi(f[6].c_str());
    p.agl = std::max(0, atoi(f[7].c_str()));
    out.push_back(p);
  }
  planes.swap(out);
  have_data = true;
  data_ms = now();
}

// ---------- Per-frame updates ----------
inline void update_positions() {
  float dt = have_data ? std::min((now() - data_ms) / 1000.0f, MAX_COAST_S) : 0.0f;
  for (auto &p : planes) {
    float miles = p.spd * 1.15078f / 3600.0f * dt;  // knots to miles moved
    float h = rad(p.hdg);
    p.x = p.x0 + sinf(h) * miles;
    p.y = p.y0 + cosf(h) * miles;
    p.d = hypotf(p.x, p.y);
  }
}

inline const Plane *find(const std::string &id) {
  for (auto &p : planes)
    if (p.id == id) return &p;
  return nullptr;
}

inline void update_ring(float ring_mi) {
  std::string cur = idx < ring.size() ? ring[idx] : "";
  size_t old_idx = idx;

  // Keep planes still inside (10% slack so a plane on the edge doesn't flicker).
  std::vector<std::string> next;
  for (auto &id : ring) {
    const Plane *p = find(id);
    if (p && p->d <= ring_mi * 1.1f) next.push_back(id);
  }
  // Add newcomers at the end, closest first if several arrive together.
  std::vector<const Plane *> fresh;
  for (auto &p : planes)
    if (p.d < ring_mi && std::find(next.begin(), next.end(), p.id) == next.end()) fresh.push_back(&p);
  std::sort(fresh.begin(), fresh.end(), [](const Plane *a, const Plane *b) { return a->d < b->d; });
  for (auto *p : fresh) next.push_back(p->id);

  ring.swap(next);
  if (ring.empty()) { idx = 0; return; }
  auto at = std::find(ring.begin(), ring.end(), cur);
  if (!cur.empty() && at != ring.end()) {
    idx = at - ring.begin();  // stay on the plane we were showing
  } else {
    idx = std::min(old_idx, ring.size() - 1);  // it left: show the next one
    shown_ms = now();
  }
}

inline void rotate() {
  if (ring.size() < 2 || running(pause_on, pause_ms, PAUSE_MS)) {
    shown_ms = now();  // fresh 6 seconds once rotation resumes
    return;
  }
  if (now() - shown_ms >= ROTATE_MS) {
    idx = (idx + 1) % ring.size();
    shown_ms = now();
  }
}

// ---------- Screens ----------
constexpr float CX = 15, CY = 16, PR = 14;  // radar center and radius in pixels

// Altitude scale on the right: ground at the bottom, each band gets its own section.
inline float alt_y(int agl) {
  if (agl < LOW_FT) return 29.0f - 9.0f * agl / LOW_FT;
  if (agl < MID_FT) return 19.0f - 8.0f * (agl - LOW_FT) / (MID_FT - LOW_FT);
  return 10.0f - 8.0f * std::min(1.0f, (float) (agl - MID_FT) / (TOP_FT - MID_FT));
}

inline void draw_right_message(Display &it, const std::string &a, const std::string &b, Color c) {
  text(it, 33 + (31 - text_w(a)) / 2, 8, a, c);
  text(it, 33 + (31 - text_w(b)) / 2, 16, b, c);
}

inline void draw_radar(Display &it, float range_mi, float ring_mi, bool stale) {
  for (int a = 0; a < 360; a += 4) px(it, CX + sinf(rad(a)) * PR, CY - cosf(rad(a)) * PR, c_dim());

  float ir = std::max(1.5f, ring_mi / range_mi * PR);
  int step = ir > 4 ? 15 : 30;
  for (int a = 0; a < 360; a += step) px(it, CX + sinf(rad(a)) * ir, CY - cosf(rad(a)) * ir, c_gray());

  float sw = (now() % SWEEP_MS) * 360.0f / SWEEP_MS;
  for (int k = 2; k < PR; k++) px(it, CX + sinf(rad(sw - 8)) * k, CY - cosf(rad(sw - 8)) * k, c_sweep_tail());
  for (int k = 2; k < PR; k++) px(it, CX + sinf(rad(sw)) * k, CY - cosf(rad(sw)) * k, c_sweep());

  std::vector<const Plane *> vis;
  for (auto &p : planes)
    if (p.d <= range_mi) vis.push_back(&p);
  // Draw high planes first so low ones end up on top.
  std::sort(vis.begin(), vis.end(), [](const Plane *a, const Plane *b) { return a->agl > b->agl; });
  int count[3] = {0, 0, 0};
  for (auto *p : vis) {
    int b = band(p->agl);
    count[b]++;
    mark(it, CX + p->x / range_mi * PR, CY - p->y / range_mi * PR, b, p->hdg);
  }
  px(it, CX, CY, c_white());  // home

  char r[8];
  snprintf(r, sizeof r, "%d", (int) roundf(range_mi));
  text(it, 0, 0, r, c_gray());  // range in miles, top left

  if (quiet_on) {  // pause symbol, bottom left: details are snoozed
    for (int y = 27; y < 32; y++) { px(it, 0, y, c_gray()); px(it, 2, y, c_gray()); }
  }

  if (running(toast_on, toast_ms, TOAST_MS)) { draw_right_message(it, toast1, toast2, c_white()); return; }
  if (stale) { draw_right_message(it, "NO", "DATA", c_gray()); return; }

  // Altitude scale along the right edge: dim section per band,
  // a bright tick for every plane at its height.
  for (int y = 20; y <= 29; y++) px(it, 63, y, band_lo(0));
  for (int y = 11; y <= 19; y++) px(it, 63, y, band_lo(1));
  for (int y = 2; y <= 10; y++) px(it, 63, y, band_lo(2));
  for (auto *p : vis) {
    float y = alt_y(p->agl);
    Color c = band_hi(band(p->agl));
    for (int x = 60; x <= 62; x++) px(it, x, y, c);
  }
  // Count and marker just inside each section.
  const int center[3] = {24, 15, 6};
  for (int b = 0; b < 3; b++) {
    mark(it, 56, center[b], b, 270);
    char n[6];
    snprintf(n, sizeof n, "%d", count[b]);
    text(it, 53 - text_w(n), center[b] - 2, n, band_hi(b));
  }
}

inline void draw_details(Display &it) {
  const Plane *p = find(ring[idx]);
  if (!p) return;
  int b = band(p->agl);
  size_t n = ring.size();

  std::string id = p->id;
  if (n > 1 && id.size() > 11) id = id.substr(0, 11);
  text(it, 1, 1, id, c_white());
  if (n > 1) {
    char s[12];
    snprintf(s, sizeof s, "%u/%u", (unsigned) (idx + 1), (unsigned) n);
    text(it, 63 - text_w(s), 1, s, c_gray());
  }

  std::string line2 = p->route;
  if (line2.empty() && p->spd > 0) line2 = std::to_string(p->spd) + "KT";
  text(it, 1, 8, line2, c_soft());

  std::string line3 = p->type.empty() ? "" : p->type + " ";
  line3 += std::to_string(p->agl) + "FT";
  text(it, 1, 15, line3, band_hi(b));

  static const char *dirs[] = {"N", "NE", "E", "SE", "S", "SW", "W", "NW"};
  float brg = fmodf(atan2f(p->x, p->y) * 180.0f / (float) M_PI + 360.0f, 360.0f);
  char line4[20];
  snprintf(line4, sizeof line4, "%.1fMI %s", p->d, dirs[(int) lroundf(brg / 45.0f) % 8]);
  text(it, 1, 22, line4, c_gray());

  // Bottom bar: fills until the next plane; gray while paused; steady with one plane.
  if (n > 1) {
    bool paused = running(pause_on, pause_ms, PAUSE_MS);
    int w = paused ? 64 : (int) (64.0f * std::min(1.0f, (now() - shown_ms) / (float) ROTATE_MS));
    for (int x = 0; x < 64; x++) px(it, x, 30, x < w ? (paused ? c_gray() : band_hi(b)) : c_bar_off());
  } else {
    for (int x = 0; x < 64; x++) px(it, x, 30, band_lo(b));
  }
}

// Called by the display every frame.
inline void render(Display &it, float range_mi, float ring_mi) {
  if (std::isnan(range_mi) || range_mi < 1) range_mi = 10;
  if (std::isnan(ring_mi) || ring_mi <= 0) ring_mi = 2;
  bool stale = !have_data || now() - data_ms > STALE_MS;
  if (have_data && stale) planes.clear();

  update_positions();
  update_ring(ring_mi);
  rotate();
  running(quiet_on, quiet_ms, QUIET_MS);
  details_now = !ring.empty() && !quiet_on;

  if (details_now) draw_details(it);
  else draw_radar(it, range_mi, ring_mi, stale);
}

// ---------- Buttons ----------
inline void show_toast(const std::string &a, const std::string &b) {
  toast1 = a; toast2 = b; toast_on = true; toast_ms = now();
}

inline float step_list(const float *list, int n, float cur, int dir) {
  if (dir > 0) {
    for (int i = 0; i < n; i++) if (list[i] > cur + 0.01f) return list[i];
    return list[n - 1];
  }
  for (int i = n - 1; i >= 0; i--) if (list[i] < cur - 0.01f) return list[i];
  return list[0];
}

inline void set_number(Number *num, float v) {
  auto call = num->make_call();
  call.set_value(v);
  call.perform();
}

// up = +1 for the Up button, -1 for Down.
inline void on_tap(int up, Number *range_n, Number *ring_n) {
  (void) ring_n;
  if (details_now && !ring.empty()) {  // Up = previous plane, Down = next
    idx = (idx + ring.size() + (up > 0 ? -1 : 1)) % ring.size();
    shown_ms = now();
    pause_on = true; pause_ms = now();
    return;
  }
  float v = step_list(RANGES, 3, range_n->state, up);  // Up = zoom out
  set_number(range_n, v);
  show_toast("RANGE", fmt_mi(v));
}

inline void on_hold(int up, Number *range_n, Number *ring_n) {
  (void) range_n;
  if (details_now) {  // back to the radar for a while
    quiet_on = true; quiet_ms = now();
    show_toast("RADAR", std::to_string(QUIET_MS / 60000) + " MIN");
    return;
  }
  float v = step_list(RINGS, 3, ring_n->state, up);  // Up = bigger ring
  set_number(ring_n, v);
  show_toast("RING", fmt_mi(v));
}

}  // namespace fr
