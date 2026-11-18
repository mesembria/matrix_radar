#pragma once
#include <cstdint>
#include <cstring>
#include <string>
namespace esphome {
inline uint32_t g_ms = 0;
inline uint32_t millis() { return g_ms; }
struct Color { uint8_t r, g, b; Color(int r_=0,int g_=0,int b_=0):r(r_),g(g_),b(b_){} };
namespace display {
struct Display { char buf[32][65]; Display(){clear();} void clear(){for(int y=0;y<32;y++){memset(buf[y],'.',64);buf[y][64]=0;}}
  void draw_pixel_at(int x,int y,Color c){ char ch='#'; if(c.r>200&&c.g<150) ch='O'; else if(c.g>150&&c.r<100) ch='G'; else if(c.b>200&&c.r<100) ch='B'; else if(c.r>200&&c.g>200) ch='W'; else if(c.r<60&&c.g<60&&c.b<60) ch=','; buf[y][x]=ch; } };
}
namespace number {
struct Number; struct NumberCall { Number *n; float v=0; void set_value(float x){v=x;} void perform(); };
struct Number { float state; NumberCall make_call(){ return NumberCall{this}; } };
inline void NumberCall::perform(){ n->state = v; }
}
}
