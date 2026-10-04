"""Гамма-таблица экрана через XRandR (ctypes, без внешних зависимостей).

То же самое делает `xsct`: одна таблица яркости на каждый канал R/G/B у каждого
активного CRTC. Здесь к температуре и яркости добавлен контраст. Формулы
температуры и яркости повторяют xsct, поэтому при контрасте 1.0 результат
совпадает с `xsct <температура> <яркость>`.
"""

import ctypes
import ctypes.util
import math

TEMPERATURE_NORM = 6500
TEMPERATURE_ZERO = 700


class _XRRScreenResources(ctypes.Structure):
    _fields_ = [
        ("timestamp", ctypes.c_ulong),
        ("configTimestamp", ctypes.c_ulong),
        ("ncrtc", ctypes.c_int),
        ("crtcs", ctypes.POINTER(ctypes.c_ulong)),
        ("noutput", ctypes.c_int),
        ("outputs", ctypes.POINTER(ctypes.c_ulong)),
        ("nmode", ctypes.c_int),
        ("modes", ctypes.c_void_p),
    ]


class _XRRCrtcGamma(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_int),
        ("red", ctypes.POINTER(ctypes.c_ushort)),
        ("green", ctypes.POINTER(ctypes.c_ushort)),
        ("blue", ctypes.POINTER(ctypes.c_ushort)),
    ]


class GammaError(Exception):
    pass


def _trim(x, lo, hi):
    return max(lo, min(hi, x))


def white_point(temp):
    """Множители каналов R, G, B (0..1) для температуры, как в xsct."""
    if temp < TEMPERATURE_NORM:
        r = 1.0
        if temp > TEMPERATURE_ZERO:
            t = math.log(temp - TEMPERATURE_ZERO)
            g = _trim(-1.47751309139817 + 0.28590164772055 * t, 0.0, 1.0)
            b = _trim(-4.38321650114872 + 0.6212158769447 * t, 0.0, 1.0)
        else:
            g = b = 0.0
    else:
        t = math.log(temp - (TEMPERATURE_NORM - TEMPERATURE_ZERO))
        r = _trim(1.75390204039018 - 0.1150805671482 * t, 0.0, 1.0)
        g = _trim(1.49221604915144 - 0.07513509588921 * t, 0.0, 1.0)
        b = 1.0
    return r, g, b


def build_ramp(size, temp, brightness, contrast, pivot=0.5):
    """Три списка по `size` значений 0..65535 (R, G, B).

    brightness и contrast — множители (1.0 = без изменений), pivot — уровень серого
    0..1, который контраст не трогает. Контраст — наклон вокруг pivot: больше 1
    уводит тона ниже pivot в тёмное, выше — в светлое (крайние обрезаются); меньше 1
    стягивает всё к pivot. Яркость и температура применяются после контраста,
    поэтому ими можно притушить даже очень контрастную картинку.
    """
    wr, wg, wb = white_point(temp)
    ramps = ([], [], [])
    for i in range(size):
        x = i / size
        y = _trim((x - pivot) * contrast + pivot, 0.0, 1.0) * brightness * 65535
        for ramp, w in zip(ramps, (wr, wg, wb)):
            ramp.append(int(y * w + 0.5))
    return ramps


class Screen:
    """Подключение к X-серверу и запись гамма-таблиц на все активные CRTC."""

    def __init__(self):
        x11 = ctypes.util.find_library("X11")
        xrandr = ctypes.util.find_library("Xrandr")
        if not x11 or not xrandr:
            raise GammaError("не найдены libX11 / libXrandr")
        self._x11 = ctypes.CDLL(x11)
        self._xr = ctypes.CDLL(xrandr)
        x, xr = self._x11, self._xr

        x.XOpenDisplay.restype = ctypes.c_void_p
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x.XDefaultRootWindow.restype = ctypes.c_ulong
        x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XCloseDisplay.argtypes = [ctypes.c_void_p]

        xr.XRRGetScreenResourcesCurrent.restype = ctypes.POINTER(_XRRScreenResources)
        xr.XRRGetScreenResourcesCurrent.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        xr.XRRFreeScreenResources.argtypes = [ctypes.POINTER(_XRRScreenResources)]
        xr.XRRGetCrtcGammaSize.restype = ctypes.c_int
        xr.XRRGetCrtcGammaSize.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        xr.XRRAllocGamma.restype = ctypes.POINTER(_XRRCrtcGamma)
        xr.XRRAllocGamma.argtypes = [ctypes.c_int]
        xr.XRRSetCrtcGamma.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                       ctypes.POINTER(_XRRCrtcGamma)]
        xr.XRRGetCrtcGamma.restype = ctypes.POINTER(_XRRCrtcGamma)
        xr.XRRGetCrtcGamma.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        xr.XRRFreeGamma.argtypes = [ctypes.POINTER(_XRRCrtcGamma)]

        self._dpy = x.XOpenDisplay(None)
        if not self._dpy:
            raise GammaError("не удалось подключиться к X-серверу")
        self._root = x.XDefaultRootWindow(self._dpy)

    def _crtcs(self):
        """Активные CRTC: [(id, размер таблицы)]."""
        res = self._xr.XRRGetScreenResourcesCurrent(self._dpy, self._root)
        if not res:
            raise GammaError("XRandR не отвечает")
        try:
            found = []
            for k in range(res.contents.ncrtc):
                crtc = res.contents.crtcs[k]
                size = self._xr.XRRGetCrtcGammaSize(self._dpy, crtc)
                if size > 0:
                    found.append((crtc, size))
            return found
        finally:
            self._xr.XRRFreeScreenResources(res)

    def set(self, temp, brightness, contrast, pivot=0.5):
        """Записать таблицу на все активные CRTC (brightness, contrast — множители,
        pivot — 0..1)."""
        crtcs = self._crtcs()
        if not crtcs:
            raise GammaError("нет активных экранов с гамма-таблицей")
        for crtc, size in crtcs:
            g = self._xr.XRRAllocGamma(size)
            try:
                channels = build_ramp(size, temp, brightness, contrast, pivot)
                for dst, values in zip((g.contents.red, g.contents.green, g.contents.blue),
                                       channels):
                    ctypes.memmove(dst, (ctypes.c_ushort * size)(*values), size * 2)
                self._xr.XRRSetCrtcGamma(self._dpy, crtc, g)
            finally:
                self._xr.XRRFreeGamma(g)
        self._x11.XSync(self._dpy, 0)

    def read(self):
        """Текущая таблица первого активного CRTC: (R, G, B) списками или None."""
        crtcs = self._crtcs()
        if not crtcs:
            return None
        crtc, size = crtcs[0]
        g = self._xr.XRRGetCrtcGamma(self._dpy, crtc)
        if not g:
            return None
        try:
            return tuple([ch[k] for k in range(size)]
                         for ch in (g.contents.red, g.contents.green, g.contents.blue))
        finally:
            self._xr.XRRFreeGamma(g)

    def matches(self, temp, brightness, contrast, pivot=0.5, tolerance=300):
        """Совпадает ли текущая таблица с расчётной (допуск в единицах 0..65535)."""
        cur = self.read()
        if not cur:
            return False
        want = build_ramp(len(cur[0]), temp, brightness, contrast, pivot)
        return all(abs(a - b) <= tolerance
                   for cur_ch, want_ch in zip(cur, want)
                   for a, b in zip(cur_ch, want_ch))

    def close(self):
        if self._dpy:
            self._x11.XCloseDisplay(self._dpy)
            self._dpy = None
