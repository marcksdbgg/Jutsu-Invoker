"""Read-only Xwayland key-state checks; no grabs, remapping or key logging."""
import ctypes
from ctypes.util import find_library
import threading
import time


class Cookie(ctypes.Structure):
    _fields_ = [('type',ctypes.c_int),('serial',ctypes.c_ulong),('send_event',ctypes.c_int),
                ('display',ctypes.c_void_p),('extension',ctypes.c_int),('evtype',ctypes.c_int),
                ('cookie',ctypes.c_uint),('data',ctypes.c_void_p)]


class Event(ctypes.Union):
    _fields_ = [('cookie',Cookie),('padding',ctypes.c_long*24)]


class RawPrefix(ctypes.Structure):
    _fields_ = [('type',ctypes.c_int),('serial',ctypes.c_ulong),('send_event',ctypes.c_int),
                ('display',ctypes.c_void_p),('extension',ctypes.c_int),('evtype',ctypes.c_int),
                ('time',ctypes.c_ulong),('deviceid',ctypes.c_int),('sourceid',ctypes.c_int),('detail',ctypes.c_int)]


class Mask(ctypes.Structure):
    _fields_ = [('deviceid',ctypes.c_int),('mask_len',ctypes.c_int),('mask',ctypes.POINTER(ctypes.c_ubyte))]


class InputGuard:
    def __init__(self, keys):
        self.lock = threading.Lock()
        self.x = ctypes.CDLL(find_library('X11') or 'libX11.so.6')
        self.x.XInitThreads()
        self.x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x.XOpenDisplay.restype = ctypes.c_void_p
        self.x.XStringToKeysym.argtypes = [ctypes.c_char_p]
        self.x.XStringToKeysym.restype = ctypes.c_ulong
        self.x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x.XKeysymToKeycode.restype = ctypes.c_uint
        self.x.XQueryKeymap.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.x.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.display = self.x.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError('No se puede comprobar el teclado de Xwayland')
        names = set(keys) | {'Shift_L','Shift_R','Control_L','Control_R','Alt_L','ISO_Level3_Shift','Super_L','Super_R','Return','Escape','Tab'}
        self.codes = {self.x.XKeysymToKeycode(self.display,self.x.XStringToKeysym(k.encode())) for k in names}
        if 0 in self.codes:
            self.close()
            raise RuntimeError('Una tecla no existe en el mapa de Xwayland')
        self._epoch = 0
        self.expected = {}
        self.text_blocked = False
        self.text_codes = {self.x.XKeysymToKeycode(self.display,self.x.XStringToKeysym(name)) for name in [b'Return',b'KP_Enter',b'backslash']}
        self.text_codes.discard(0);self.text_codes.add(51)  # evdev KEY_BACKSLASH
        self.escape_code = self.x.XKeysymToKeycode(self.display,self.x.XStringToKeysym(b'Escape'))
        self.focus_probe = lambda:False
        self.tracking_available = False
        # Xwayland/evdev FK13..FK17 are keycodes 191..195. Their keysyms can be
        # absent (or XF86 aliases), so resolving F13 by keysym alone is insufficient.
        self.virtual_codes = set(range(191,196)) | {code for i in range(13,18)
            if (code:=self.x.XKeysymToKeycode(self.display,self.x.XStringToKeysym(f'F{i}'.encode())))}
        # XI2 observes input without grabbing it. Only a counter survives each
        # drain; no key names, timestamps or pointer coordinates are retained.
        try:
            self.x.XDefaultRootWindow.argtypes=[ctypes.c_void_p];self.x.XDefaultRootWindow.restype=ctypes.c_ulong
            self.x.XQueryExtension.argtypes=[ctypes.c_void_p,ctypes.c_char_p,*([ctypes.POINTER(ctypes.c_int)]*3)]
            self.x.XPending.argtypes=[ctypes.c_void_p];self.x.XNextEvent.argtypes=[ctypes.c_void_p,ctypes.POINTER(Event)]
            self.x.XGetEventData.argtypes=[ctypes.c_void_p,ctypes.POINTER(Cookie)]
            self.x.XFreeEventData.argtypes=[ctypes.c_void_p,ctypes.POINTER(Cookie)]
            self.x.XSync.argtypes=[ctypes.c_void_p,ctypes.c_int]
            self.xi=ctypes.CDLL(find_library('Xi') or 'libXi.so.6')
            self.xi.XIQueryVersion.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_int)]
            self.xi.XISelectEvents.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(Mask),ctypes.c_int]
            opcode=ctypes.c_int();other=ctypes.c_int();error=ctypes.c_int()
            major=ctypes.c_int(2);minor=ctypes.c_int(0)
            if not self.x.XQueryExtension(self.display,b'XInputExtension',ctypes.byref(opcode),ctypes.byref(other),ctypes.byref(error)) or self.xi.XIQueryVersion(self.display,ctypes.byref(major),ctypes.byref(minor)):
                raise RuntimeError('XI2 no disponible')
            self.opcode=opcode.value
            bits=(ctypes.c_ubyte*2)(0,(1<<(13-8))|(1<<(15-8)))
            mask=Mask(1,2,bits)  # XIAllMasterDevices, RawKeyPress, RawButtonPress
            if self.xi.XISelectEvents(self.display,self.x.XDefaultRootWindow(self.display),ctypes.byref(mask),1):
                raise RuntimeError('XI2 no disponible')
            self.x.XSync(self.display,0);self.tracking_available=True
        except (OSError,AttributeError,RuntimeError):
            pass  # Completion will use three fresh orbs instead of a shadow.

    def _drain(self):
        while self.tracking_available and self.display and self.x.XPending(self.display):
            event=Event();self.x.XNextEvent(self.display,ctypes.byref(event))
            cookie=event.cookie
            if cookie.type!=35 or cookie.extension!=self.opcode or not self.x.XGetEventData(self.display,ctypes.byref(cookie)):
                continue
            try:
                raw=ctypes.cast(cookie.data,ctypes.POINTER(RawPrefix)).contents
                self._observe(raw)
            finally:self.x.XFreeEventData(self.display,ctypes.byref(cookie))

    def _observe(self,raw):
        expected=self.expected.get(raw.detail,[])
        expected[:]=[deadline for deadline in expected if deadline>=time.monotonic()]
        if raw.evtype==13 and expected:
            expected.pop(0);return
        if raw.evtype==13 and raw.detail in self.text_codes and self.focus_probe():
            self.text_blocked=True
        if raw.evtype==13 and raw.detail==self.escape_code and self.focus_probe():
            self.text_blocked=False
        if raw.evtype==13 and raw.detail not in self.virtual_codes or raw.evtype==15 and raw.detail==1:
            self._epoch+=1

    def expect(self,key):
        with self.lock:
            self._drain()
            code=self.x.XKeysymToKeycode(self.display,self.x.XStringToKeysym(key.encode()))
            if not code:raise RuntimeError('Tecla de envío ausente en Xwayland')
            self.expected.setdefault(code,[]).append(time.monotonic()+.3)

    @property
    def blocked(self):
        with self.lock:
            self._drain();return self.text_blocked

    @property
    def epoch(self):
        with self.lock:
            self._drain();return self._epoch

    def clear(self):
        with self.lock:
            self._drain()
            bits = (ctypes.c_ubyte * 32)()
            if self.text_blocked or not self.display or not self.x.XQueryKeymap(self.display,bits):
                return False
            return not any(bits[k//8] & (1 << (k%8)) for k in self.codes)

    def close(self):
        if self.display:
            self.x.XCloseDisplay(self.display)
            self.display = None
