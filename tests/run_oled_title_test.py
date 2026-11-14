"""Exercise production title rendering on the host, without building firmware."""
from pathlib import Path
import os
import re
import subprocess

root = Path(__file__).resolve().parents[1]
source = (root / 'src/oled_status.cpp').read_text(encoding='utf-8')
version = re.search(r'set\(VERSION "([^"]+)"', (root / 'CMakeLists.txt').read_text()).group(1)
out = root.parent / 'DS5Dongle-Studio-build/reports/oled-title-scroll'
out.mkdir(parents=True, exist_ok=True)
compiler = root.parent / 'DS5Dongle-Studio-build/source/toolchain/mingw64/mingw64/bin/g++.exe'

def function(signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2]

code = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include "oled_font.h"
constexpr int kWidth=128,kHeight=64,kRowBytes=16;
uint8_t framebuffer[kRowBytes*kHeight]{};
uint32_t title_step_ms=0;
int title_offset=0;
'''
code += '#define PICO_PROGRAM_VERSION_STRING "' + version + '"\n'
code += function('void set_pixel(') + '\n' + function('void draw_title(')
code += r'''
void check(uint32_t now) {
    memset(framebuffer,0,sizeof(framebuffer));
    draw_title(now);
    const char text[]="Studio-DS5Light v" PICO_PROGRAM_VERSION_STRING "   ";
    const int width=(sizeof(text)-1)*6;
    for(int y=0;y<64;++y) for(int x=0;x<128;++x) {
        bool expected=false;
        if(x>=1 && x<49 && y>=1 && y<8) {
            int p=(title_offset+x-1)%width;
            expected=p%6<5 && (kFont5x7[text[p/6]-32][p%6] & (1u<<(y-1)));
        }
        bool actual=framebuffer[y*16+x/8] & (1u<<(7-x%8));
        assert(actual==expected);
    }
}
int main() {
    check(0);check(999);assert(title_offset==0);
    check(1000);assert(title_offset==1);
    check(1124);assert(title_offset==1);
    check(1125);assert(title_offset==2);
    // Every position, including the version, trailing gap and repeat boundary.
    const char text[]="Studio-DS5Light v" PICO_PROGRAM_VERSION_STRING "   ";
    const int width=(sizeof(text)-1)*6;
    for(int i=2;i<width;++i) check(title_step_ms+125);
    assert(title_offset==0);
    uint32_t start=title_step_ms;
    check(start+999);assert(title_offset==0);
    check(start+1000);assert(title_offset==1);
    // A delayed frame advances once rather than jumping through unread text.
    check(title_step_ms+5000);assert(title_offset==2);
    title_offset=0;title_step_ms=UINT32_MAX-499;
    check(499);assert(title_offset==0);
    check(500);assert(title_offset==1);
    puts("OLED title: clipping, spacing, full cycle, pauses and clock wrap PASS");
}
'''
cpp = out / 'oled_title.cpp'
exe = out / 'oled_title.exe'
cpp.write_text(code, encoding='utf-8')
env = dict(os.environ)
env['PATH'] = str(compiler.parent) + os.pathsep + env.get('PATH', '')
subprocess.run([str(compiler), '-std=c++17', '-Wall', '-Wextra', '-I' + str(root / 'src'), str(cpp), '-o', str(exe)], env=env, check=True)
subprocess.run([str(exe)], env=env, check=True)
assert re.search(r'if \(!panel_enabled\) \{\s*reset_graph_state\(\);\s*title_offset = 0;\s*title_step_ms = now;', source)
assert 'draw_title(now);' in function('void draw_status(')
print('Build version ' + version + '; title restart on panel wake PASS')
