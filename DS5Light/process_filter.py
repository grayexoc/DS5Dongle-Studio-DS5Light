"""Name-only exclusions for process discovery and display; no extra OS queries."""
import ntpath


# Exact names keep common Windows services out without hiding every executable
# whose name happens to contain a Windows component's name.
SYSTEM_NAMES=frozenset({
    'system','system idle process','registry','secure system','memory compression',
    'svchost.exe','conhost.exe','csrss.exe','smss.exe','wininit.exe','services.exe',
    'lsass.exe','lsaiso.exe','fontdrvhost.exe','dwm.exe','winlogon.exe','logonui.exe',
    'spoolsv.exe','sppsvc.exe','wlanext.exe','ctfmon.exe','unsecapp.exe',
    'searchhost.exe','searchindexer.exe','searchprotocolhost.exe','searchfilterhost.exe',
    'applicationframehost.exe','backgroundtaskhost.exe','useroobebroker.exe',
    'systemsettings.exe','systemsettingsbroker.exe','musnotification.exe',
    'musnotificationux.exe','usoclient.exe','mousocoreworker.exe','tiworker.exe',
    'trustedinstaller.exe','wermgr.exe','werfault.exe','werfaultsecure.exe',
    'smartscreen.exe','compattelrunner.exe','sgrmbroker.exe',
    'tasklist.exe','processcapture.exe',
})

USER_RULES=tuple(line.strip().casefold() for line in '''
runtimebroker
msiafterburner
rtss
idman
taskhostw
steamwebhelper
steam
shellexperiencehost
chatgpt
codex
node.exe
cmd.exe
identify_helper
textinputhost
colorveil
securityhealth
dllhost
seathhost
startmenu
crossdeviceresume
shellhost
explorer
lgtvdaemon.exe
sihost.exe
defendersessionhelper
audiodg.exe
dashost.exe
lgtvsvc.exe
mpdefender
nvdisplay.
nissrv.exe
msmpeng.exe
secure system
steamservice
winlogon
wmiprvse.exe
wudfhost.exe
adobe
dataexchangehost
chxsmartscreen
midisrv
'''.splitlines() if line.strip())


def _has_extension(rule):
    # A trailing dot ("nvdisplay.") is a keyword, not a file extension.
    return bool(ntpath.splitext(rule)[1].strip('.'))


EXACT_NAMES=SYSTEM_NAMES|frozenset(rule for rule in USER_RULES if _has_extension(rule))
KEYWORDS=tuple(rule for rule in USER_RULES if not _has_extension(rule))


def is_excluded_process(name):
    if not isinstance(name,str):return True
    # Match the executable name only, never the installation directory.
    name=ntpath.basename(name).strip().casefold()
    return not name or name in EXACT_NAMES or any(keyword in name for keyword in KEYWORDS)
