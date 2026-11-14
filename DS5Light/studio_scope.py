"""Native editor scope; hidden/construction values are never targeted by reads/writes."""
from studio_fields import FIELDS, SECTIONS
AUDIO_HAPTIC_CHILDREN=frozenset(f[1] for section in SECTIONS if section["title"]=="Auto-Haptics & Speaker Effect Leak" for f in section["fields"] if f[1]!="auto_haptics_enable")
TRIGGER_FIELDS = frozenset(
    prefix + suffix
    for prefix in ('at_', 'at_l2_')
    for suffix in ('mode', 'shape', 'strength', 'strength_b', 'start_pos', 'detent_pos', 'threshold', 'pushback', 'kick_style', 'pushback_freq')
)
TRIGGER_FIELDS |= frozenset(('at_pushback_src', 'synth_force', 'ce_r2_enable', 'ce_l2_enable', 'ce_r2_yield', 'ce_l2_yield'))
FAST_TRIGGER_FIELDS = frozenset(prefix + suffix for prefix in ('t2_', 't2_l2_')
                               for suffix in ('mode', 'pos', 'button'))
TRIGGER_FIELDS |= FAST_TRIGGER_FIELDS
CONSTRUCTION = frozenset(k for k in FIELDS if k.startswith(('at_','t2_','ce_')) and k not in TRIGGER_FIELDS)
REMOVED = frozenset(k for k in FIELDS if k=='disable_usb_sn' or k.startswith(('effect_leak_','batt_','touch_mouse')))
EDITABLE = {k:f for k,f in FIELDS.items() if k not in CONSTRUCTION | REMOVED}
LIGHTBAR_FIELDS=frozenset(('lightbar_fixed','lightbar_rgb'))
RUMBLE_FIELDS=frozenset(('rumble_gain','rumble_release'))
USB_MODE_FIELDS=frozenset(('usb_gamepad_mode',))
RUMBLE_MODE_FIELDS=frozenset(('rumble_mode',))
EDGE_SERIAL_FIELDS=frozenset(('disable_usb_sn',))
OPTIONAL_FIELDS=LIGHTBAR_FIELDS | RUMBLE_FIELDS | USB_MODE_FIELDS | RUMBLE_MODE_FIELDS | EDGE_SERIAL_FIELDS
SUPPORTED_CONFIGS=(19,20,21,22)
def config_version(values):
    if USB_MODE_FIELDS.issubset(values):return 22
    return 21 if RUMBLE_FIELDS.issubset(values) else 20 if LIGHTBAR_FIELDS.issubset(values) else 19
def trigger_display(raw):return 10 - float(raw)*.9
def trigger_raw(value):return max(0,min(10,round((10-float(value))/.9)))
