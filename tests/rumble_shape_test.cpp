#include "rumble_shape.h"
#include <cassert>
#include <cstdio>
int main() {
    RumbleShape p;
    uint8_t l=101,r=30;
    p.apply(l,r,0,100,0);assert(l==101&&r==30&&!p.active());
    l=0;r=0;p.apply(l,r,1,100,0);assert(!l&&!r&&!p.active());
    l=100;r=200;p.apply(l,r,10,200,0);assert(l==200&&r==255);
    l=100;r=40;p.apply(l,r,20,100,1);assert(l==100&&r==40);
    l=r=0;p.apply(l,r,21,100,1);assert(l==100&&r==40&&p.active());
    l=r=0;p.apply(l,r,31,100,1);assert(l==50&&r==20); // same target does not restart
    assert(p.active()); // deadline alone cannot cancel the final scheduler tick
    l=r=0;p.apply(l,r,41,100,1);assert(l==0&&r==0&&!p.active());
    l=200;r=100;p.apply(l,r,50,100,2);
    l=r=0;p.apply(l,r,51,100,2);
    l=r=0;p.apply(l,r,71,100,2);assert(l==100&&r==50);
    l=30;r=200;p.apply(l,r,72,100,2);assert(l==30&&r==200); // fresh attack replaces tail
    l=10;r=0;p.apply(l,r,73,100,2);
    l=10;r=0;p.apply(l,r,113,100,2);assert(l==10&&r==0&&!p.active());
    l=r=200;p.apply(l,r,0xfffffff0u,100,1);
    l=r=0;p.apply(l,r,0xfffffff1u,100,1);
    l=r=0;p.apply(l,r,5,100,1);assert(!l&&!r&&!p.active()); // clock wrap
    l=r=200;p.apply(l,r,10,100,1);l=r=0;p.apply(l,r,11,100,1);
    p.reset();l=r=0;p.apply(l,r,12,100,1);assert(!l&&!r&&!p.active());
    l=r=200;p.apply(l,r,20,100,1);l=r=0;p.apply(l,r,21,100,1);
    l=r=0;p.apply(l,r,22,150,0);assert(!l&&!r&&!p.active()); // live setting change clears tail
    puts("PASS: default identity, gain/clamp, independent channels, 20/40ms release, final zero, attack priority, reset, wrap");
}
