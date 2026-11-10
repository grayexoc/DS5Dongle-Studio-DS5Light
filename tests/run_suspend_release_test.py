"""Real main suspend scheduler + transport pump + acknowledgement policy, no hardware."""
from pathlib import Path
import os
import subprocess

root = Path(__file__).resolve().parents[1]
base = root.parent / 'DS5Dongle-Studio-build'
out = base / 'reports/suspend-release-tests'
out.mkdir(parents=True, exist_ok=True)
state = (root / 'src/state_mgr.cpp').read_text(encoding='utf-8')
main = (root / 'src/main.cpp').read_text(encoding='utf-8')
fixture = (base / 'reports/audit-fixes/native-continuity.cpp').read_text(encoding='utf-8')
fixture = fixture[:fixture.index('int main(){')]
start = state.index('void state_suspend_release_sent(')
ack = state[start:state.index('\n}', start) + 2]
fixture = fixture.replace('void state_suspend_release_sent(const uint8_t*){}', ack)
fixture = fixture.replace('void state_set(uint8_t*p,unsigned n){memset(p,0,n);}',
    'void state_set(uint8_t*p,unsigned n){memset(p,0,n);p[0]=13;p[10]=p[21]=5;}')
start = main.index('            static bool was_suspended = false;')
tick = main[start:main.index('\n        }\n        {', start)]
code = fixture + r'''
struct SetStateData {uint8_t data[63];};
int reportSeqCounter=0,release_requests=0;
bool suspended=false;
bool wake_host_is_suspended(){return suspended;}
bool bt_is_connected(){return hid_interrupt_cid!=0;}
bool state_release_for_suspend(){++release_requests;suspend_release_pending=true;return true;}
''' + next(line for line in state.splitlines() if line.startswith('void state_cancel_suspend_release()')) + r'''
void main_tick(){
''' + tick + r'''
}
int main(){
 now=100;suspended=true;main_tick();assert(suspend_release_pending&&send_fifo.size()==1);
 status=1;for(int i=0;i<3;i++)pump();
 assert(suspend_release_pending&&!pending_send_valid&&send_fifo.empty());
 now=139;main_tick();assert(send_fifo.empty());
 now=140;main_tick();assert(send_fifo.size()==1);
 status=0;pump();assert(!suspend_release_pending&&delivered.size()==1);
 now=1000;main_tick();assert(send_fifo.empty()&&release_requests==1); // no periodic OFF after ACK
 suspended=false;main_tick();
 // Expiring the head's retry budget also preserves the suspend-level intent.
 now=1020;suspended=true;main_tick();status=1;pump();
 now=1060;status=0;pump();assert(suspend_release_pending&&send_fifo.empty());
 main_tick();pump();assert(!suspend_release_pending);
 suspended=false;main_tick();
 // A stale matching OFF ahead of a queued START cannot acknowledge the new release.
 uint8_t off[78]{};off[0]=0x31;off[3]=13;off[13]=off[24]=5;
 uint8_t on[78]{};on[0]=0x31;on[3]=15;on[5]=100;
 bt_write(off,78);bt_write(on,78);
 suspended=true;now=1100;main_tick();
 pump();assert(suspend_release_pending);
 pump();assert(suspend_release_pending);
 pump();assert(!suspend_release_pending&&send_fifo.empty());
 suspended=false;main_tick();
 // Failed queue admission must not lose the release intent.
 for(int i=0;i<30;i++){on[5]=i+1;bt_write(on,78);}
 suspended=true;now=1200;main_tick();assert(suspend_release_pending);
 while(pending_send_valid||!send_fifo.empty())pump();
 assert(suspend_release_pending);
 now=1240;main_tick();pump();assert(!suspend_release_pending);
 // Time arithmetic remains valid across the 32-bit millisecond wrap.
 suspended=false;main_tick();now=0xfffffff0;suspended=true;main_tick();
 status=1;for(int i=0;i<3;i++)pump();assert(suspend_release_pending);
 now=16;main_tick();assert(send_fifo.empty());
 now=24;main_tick();status=0;pump();assert(!suspend_release_pending);
 // Resume cancels pending retries without restarting synthesis in this scheduler.
 suspended=false;main_tick();now=100;suspended=true;main_tick();
 status=1;for(int i=0;i<3;i++)pump();assert(suspend_release_pending);
 suspended=false;main_tick();assert(!suspend_release_pending);
 now=200;main_tick();assert(send_fifo.empty());
 puts("PASS: suspend OFF retry, ACK drain barrier, queue-full recovery, no repeated OFF after ACK, timer wrap and resume cancellation");
}
'''
cpp = out / 'test.cpp';cpp.write_text(code, encoding='utf-8')
bin_dir = base / 'source/toolchain/mingw64/mingw64/bin'
env = dict(os.environ);env['PATH'] = str(bin_dir) + os.pathsep + env.get('PATH', '')
subprocess.run([str(bin_dir / 'g++.exe'), '-std=c++17', '-I'+str(root / 'src'),
                str(cpp), '-o', str(out / 'test.exe')], env=env, check=True)
result = subprocess.run([str(out / 'test.exe')], env=env, capture_output=True, text=True)
(out / 'result.txt').write_text(result.stdout + result.stderr, encoding='utf-8')
print(result.stdout + result.stderr);result.check_returncode()
