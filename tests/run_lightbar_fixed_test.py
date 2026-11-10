"""Host-only test. Does not build or flash firmware or access a device."""
from pathlib import Path
import os, re, subprocess

root = Path(__file__).resolve().parents[1]
out = root.parent / 'DS5Dongle-Studio-build' / 'reports' / 'lightbar-fixed-tests'
out.mkdir(parents=True, exist_ok=True)
source = (root / 'src/config.cpp').read_text(encoding='utf-8')
start = source.index('static void config_body_valid(Config_body &value) {')
end = source.index('\n}', start) + 2
version = re.search(r'constexpr uint16_t CONFIG_VERSION = \d+;', source).group()
def function(signature):
    first = source.index(signature)
    return source[first:source.index('\n}', first)+2]
utils = (root/'src/utils.h').read_text(encoding='utf-8')
crc = utils[utils.index('inline constexpr uint32_t crc32_table_entry'):utils.index('inline void fill_output_report_checksum')]
fixture = '''
static uint8_t fixture_name[SLOT_NAME_LEN]{};
static Config_body fixture_body{}, g_active_snapshot{};
static int16_t g_active_slot = -1;
static bool g_active_snapshot_valid = false;
static bool slot_read(uint8_t slot, uint8_t *name, Config_body &body) {
    if (slot != 1) return false;
    memcpy(name, fixture_name, SLOT_NAME_LEN); body = fixture_body; return true;
}
'''
(out / 'lightbar_config_extract.h').write_text('#include <array>\n' + version + '\n' + source[start:end] + '\n' + crc + fixture +
    function('static uint32_t resume_slot_fingerprint(') + '\n' +
    function('bool active_profile_restore('), encoding='utf-8')
bin_dir = root.parent / 'DS5Dongle-Studio-build/source/toolchain/mingw64/mingw64/bin'
env = dict(os.environ)
env['PATH'] = str(bin_dir) + os.pathsep + env.get('PATH', '')
exe = out / 'lightbar_fixed_test.exe'
subprocess.run([str(bin_dir/'g++.exe'), '-std=c++17', '-Wall', '-Wextra',
    '-I'+str(root/'src'), '-I'+str(out), str(root/'tests/lightbar_fixed_test.cpp'), '-o', str(exe)],
    env=env, check=True)
completed = subprocess.run([str(exe)], env=env, check=True, capture_output=True, text=True)
(out/'result.txt').write_text(completed.stdout, encoding='utf-8')
print(completed.stdout)
