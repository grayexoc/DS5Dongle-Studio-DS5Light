"""Optional global microphone-button shortcut: existing hidapi + Windows SendInput.



No device writes, keyboard hooks, driver installation, process selection or audio

engine dependency. The default is off; disabled workers sleep without HID scans.

"""

from thread_start import start_thread
from studio_i18n import text as _ui_tr
import ctypes

from ctypes import wintypes

import os

import queue

import threading

import time





MODIFIERS = {'Ctrl': 0xA2, 'Alt': 0xA4, 'Shift': 0xA0, 'Win': 0x5B}

KEYS = {f'F{i}': 0x6F+i for i in range(1, 25)}

KEYS.update({ch: ord(ch) for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'})

KEYS.update({

    'Space': 0x20, 'Enter': 0x0D, 'Tab': 0x09, 'Escape': 0x1B,

    'Backspace': 0x08, 'Delete': 0x2E, 'Insert': 0x2D,

    'Home': 0x24, 'End': 0x23, 'PageUp': 0x21, 'PageDown': 0x22,

    'Up': 0x26, 'Down': 0x28, 'Left': 0x25, 'Right': 0x27,

    'PrintScreen': 0x2C, 'Pause': 0x13,

    'VolumeMute': 0xAD, 'VolumeDown': 0xAE, 'VolumeUp': 0xAF,

    'MediaPlayPause': 0xB3, 'MediaNext': 0xB0, 'MediaPrevious': 0xB1,

})





def default_binding():

    return {'enabled': False, 'key': 'F8', 'modifiers': []}





def validate_binding(value):

    if not isinstance(value, dict) or set(value) != {'enabled', 'key', 'modifiers'}:

        raise ValueError(_ui_tr('마이크 버튼 키보드매핑 설정 형식 오류'))

    if type(value['enabled']) is not bool or not isinstance(value['key'], str) or value['key'] not in KEYS:

        raise ValueError(_ui_tr('마이크 버튼 키보드매핑 설정 값 오류'))

    mods = value['modifiers']

    if not isinstance(mods, list) or any(not isinstance(m, str) or m not in MODIFIERS for m in mods) or len(set(mods)) != len(mods):

        raise ValueError(_ui_tr('마이크 버튼 키보드매핑 조합 오류'))

    if value['key'] == 'Delete' and 'Ctrl' in mods and 'Alt' in mods:

        raise ValueError(_ui_tr('Ctrl + Alt + Delete는 지원하지 않습니다.'))

    return dict(enabled=value['enabled'], key=value['key'], modifiers=[m for m in MODIFIERS if m in mods])





def binding_label(value):

    return ' + '.join([*value['modifiers'], value['key']])





class _KeyboardInput(ctypes.Structure):

    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD),

                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD),

                ('dwExtraInfo', ctypes.c_size_t)]





class _MouseInput(ctypes.Structure):

    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG),

                ('mouseData', wintypes.DWORD), ('dwFlags', wintypes.DWORD),

                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]





class _InputValue(ctypes.Union):

    _fields_ = [('ki', _KeyboardInput), ('mi', _MouseInput)]





class _Input(ctypes.Structure):

    _anonymous_ = ('value',)

    _fields_ = [('type', wintypes.DWORD), ('value', _InputValue)]





class WindowsKeyboard:

    def __init__(self):

        if os.name != 'nt':

            raise OSError(_ui_tr('Windows 전용 기능입니다.'))

        self.api = ctypes.WinDLL('user32', use_last_error=True)

        self.api.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int]

        self.api.SendInput.restype = wintypes.UINT

        self.api.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]

        self.api.MapVirtualKeyW.restype = wintypes.UINT

        self.api.GetAsyncKeyState.argtypes = [ctypes.c_int]

        self.api.GetAsyncKeyState.restype = ctypes.c_short

        self.api.GetForegroundWindow.argtypes = []

        self.api.GetForegroundWindow.restype = wintypes.HWND

        self.api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

        self.api.GetWindowThreadProcessId.restype = wintypes.DWORD



    def available(self, keys):

        pid = wintypes.DWORD()

        self.api.GetWindowThreadProcessId(self.api.GetForegroundWindow(), ctypes.byref(pid))

        # Do not type into our own controls or interfere with held modifiers.

        if pid.value == os.getpid():

            return False

        checked = {*keys, 0x10, 0x11, 0x12, 0x5B, 0x5C}

        return not any(self.api.GetAsyncKeyState(key) & 0x8000 for key in checked)



    def send(self, keys, released=False):

        inputs = (_Input * len(keys))()

        for item, key in zip(inputs, keys):

            scan = self.api.MapVirtualKeyW(key, 4)  # MAPVK_VK_TO_VSC_EX

            flags = 2 if released else 0

            # Pause/PrintScreen and media keys retain their virtual-key form.

            if key not in (0x13, 0x2C) and key < 0xAD and scan and scan >> 8 in (0, 0xE0):

                flags |= 8 | (1 if scan >> 8 == 0xE0 else 0)

                vk, scan = 0, scan & 0xFF

            else:

                vk, scan = key, 0

            item.type = 1

            item.ki = _KeyboardInput(vk, scan, flags, 0, 0x4453354C)

        return self.api.SendInput(len(inputs), inputs, ctypes.sizeof(_Input))





class MuteShortcut:

    """Two sleeping workers: HID read notifications and bounded key taps."""

    def __init__(self):

        self._lock = threading.Lock()

        self._binding = default_binding()

        self._version = 0

        self._session = 0

        self._connected = False

        self._link_status = _ui_tr('꺼짐')

        self._result = None

        self._result_time = 0.

        self.last_error = None

        self._stop = threading.Event()

        self._wake = threading.Event()

        self._jobs = queue.Queue(maxsize=4)

        self._reader = self._sender = None



    def configure(self, value):

        clean = validate_binding(value)

        with self._lock:

            if clean == self._binding or self._stop.is_set():

                return

            self._binding = clean

            self._version += 1

            self._session += 1

            self._connected = False

            self._link_status = _ui_tr('연결 대기') if clean['enabled'] else _ui_tr('꺼짐')

            self._result = None

            start = clean['enabled'] and self._reader is None

            if start:

                self._reader = threading.Thread(target=self._read, name='DS5Light mute HID', daemon=True)

                self._sender = threading.Thread(target=self._send, name='DS5Light shortcut', daemon=True)

        self._wake.set()

        if start:

            start_thread(self._reader)

            start_thread(self._sender)



    def status(self):

        with self._lock:

            if not self._binding['enabled']:

                return _ui_tr('꺼짐')

            if self._result and time.monotonic()-self._result_time < 3:

                return self._result

            return self._link_status



    def _link(self, version, connected, status):

        with self._lock:

            if version != self._version or self._stop.is_set():

                return

            if self._connected != connected:

                self._session += 1

            self._connected = connected

            if status is not None:

                self._link_status = status



    def _feedback(self, version, status, error=None):

        with self._lock:

            if version == self._version and not self._stop.is_set():

                self._result, self._result_time = status, time.monotonic()

                self.last_error = str(error) if error else None



    def _wait(self, version, timeout=None):

        self._wake.clear()

        if version == self._version and not self._stop.is_set():

            self._wake.wait(timeout)



    def _enqueue(self, version):

        with self._lock:

            if version != self._version or not self._connected or not self._binding['enabled']:

                return

            binding = self._binding

            job = (version, self._session, time.monotonic(), binding['key'], tuple(binding['modifiers']))

        try:

            self._jobs.put_nowait(job)

        except queue.Full:

            self._feedback(version, _ui_tr('입력 대기 초과'))



    def _read(self):

        while not self._stop.is_set():

            version = self._version

            if not self._binding['enabled']:

                self._wait(version)

                continue

            device = None

            try:

                import hid

                # Exactly one Sony USB gamepad collection: never pick an

                # arbitrary controller when several are attached.

                candidates = {d['path'] for d in hid.enumerate(0x054C, 0)

                              if d.get('product_id') in (0x0CE6, 0x0DF2)

                              and d.get('usage_page') == 1 and d.get('usage') in (4, 5)

                              and d.get('bus_type', 1) in (0, 1)}

                if len(candidates) != 1:

                    self._link(version, False, _ui_tr('장치 여러 개') if candidates else _ui_tr('연결 대기'))

                    self._wait(version, 2.)

                    continue

                device = hid.device()

                device.open_path(next(iter(candidates)))

                pressed = None

                sensor = None

                last_fresh = time.monotonic()

                while not self._stop.is_set() and version == self._version:

                    raw = device.read(64, 100)

                    now = time.monotonic()

                    if not raw:

                        if pressed is not None and now-last_fresh > .5:

                            self._link(version, False, _ui_tr('연결 대기'))

                            pressed = None

                        continue

                    if len(raw) != 64 or raw[0] != 0x01:

                        self._link(version, False, _ui_tr('입력 형식 확인 필요'))

                        pressed = None

                        continue

                    # Payload sensor timestamp at 27..30. Studio can repeat the

                    # last USB report after BT loss: repetitions are not presses.

                    stamp = bytes(raw[28:32])

                    if stamp == sensor:

                        if pressed is not None and now-last_fresh > .5:

                            self._link(version, False, _ui_tr('연결 대기'))

                            pressed = None

                        continue

                    sensor, last_fresh = stamp, now

                    down = bool(raw[10] & 0x04)  # report ID + payload byte 9

                    if pressed is None:

                        # Establish a baseline; connecting with Mute held must

                        # not trigger a Windows shortcut.

                        self._link(version, True, _ui_tr('연결됨'))

                    elif down and not pressed:

                        self._enqueue(version)

                    pressed = down

            except Exception as exc:

                self._link(version, False, _ui_tr('HID 접근 실패'))

                self.last_error = str(exc)

            finally:

                self._link(version, False, None)

                if device is not None:

                    try:

                        device.close()

                    except Exception:

                        pass

            self._wait(version, 2.)



    def _send(self):

        keyboard = None

        while not self._stop.is_set():

            job = self._jobs.get()

            if job is None:

                return

            version, session, created, key, mods = job

            with self._lock:

                valid = (version == self._version and session == self._session

                         and self._binding['enabled'] and self._connected)

            if not valid or time.monotonic()-created > .25 or self._stop.is_set():

                continue

            keys = [*(MODIFIERS[m] for m in mods), KEYS[key]]

            attempted = False

            try:

                if keyboard is None:

                    keyboard = WindowsKeyboard()

                if not keyboard.available(keys):

                    self._feedback(version, _ui_tr('키보드 입력 중 · 생략'))

                    continue

                # Recheck after the OS calls; configuration/disconnect may have

                # invalidated a queued press while the sender was waking up.

                with self._lock:

                    if version != self._version or session != self._session or self._stop.is_set():

                        continue

                    attempted = True

                    sent = keyboard.send(keys)

                if sent != len(keys):

                    raise OSError('SendInput key-down failed; target permissions or input filtering may block it.')

                # A brief tap helps games which sample held keys. The HID and

                # audio workers continue independently throughout this interval.

                self._stop.wait(.03)

                self._feedback(version, _ui_tr('입력 전달됨'))

            except Exception as exc:

                self._feedback(version, _ui_tr('키 입력 실패'), exc)

            finally:

                if attempted:

                    try:

                        released = keyboard.send(list(reversed(keys)), released=True)

                        if released != len(keys):

                            # A single bounded retry; never loop injecting keys.

                            self._stop.wait(.01)

                            if keyboard.send(list(reversed(keys)), released=True) != len(keys):

                                raise OSError('SendInput key-up failed')

                    except Exception as exc:

                        self._feedback(version, _ui_tr('키 해제 실패'), exc)



    def close(self):

        self._stop.set()

        self._wake.set()

        while True:

            try:

                self._jobs.get_nowait()

            except queue.Empty:

                break

        self._jobs.put_nowait(None)

        for thread in (self._reader, self._sender):

            if thread:

                thread.join(timeout=.5)

