#include "../esphome/flight_radar.h"
#include <iostream>
using namespace esphome;
void dump(const char*title){ display::Display d; fr::render(d, 10, 2); std::cout << "== " << title << " (details=" << fr::details_now << ", ring=" << fr::ring.size() << ")\n"; for(int y=0;y<32;y++) std::cout << d.buf[y] << "\n"; }
int main(){
  number::Number range{10}, ringn{2};
  g_ms = 1000; dump("no data yet");
  // airliner far, GA low near, mid plane
  fr::parse(" UA1482,DEN>SFO,B738,-52,31,270,280,18500;N172SP,,C172,40,-20,315,100,1400;N815SR,,SR22,-60,-50,45,150,4500;F91307,DEN>MSP,A21N,80,70,30,300,25000");
  g_ms = 2000; dump("radar");
  // a plane enters ring
  fr::parse("UA1482,DEN>SFO,B738,-52,31,270,280,18500;N172SP,,C172,10,-5,315,100,1400;N4417K,,PA28,-8,6,120,95,2200;F91307,DEN>MSP,A21N,80,70,30,300,25000");
  g_ms = 3000; dump("details 1");
  g_ms = 9500; dump("after 6.5 s rotate");
  fr::on_tap(-1, &range, &ringn); g_ms = 9600; dump("tap down (next, paused)");
  fr::on_hold(1, &range, &ringn); g_ms = 9700; dump("hold -> quiet + toast");
  g_ms = 13000; dump("quiet radar");
  fr::on_tap(1, &range, &ringn); g_ms = 13100; std::cout << "range now " << range.state << "\n"; 
  fr::on_hold(-1, &range, &ringn); std::cout << "ring now " << ringn.state << "\n";
  g_ms = 200000; dump("stale");
  std::cout << fr::fmt_mi(1.5) << "|" << fr::fmt_mi(10) << "\n";
}
