from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_MOUSEWHEEL = 0x020A
WHEEL_DELTA = 120

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

MONITORINFOF_PRIMARY = 0x1
MONITOR_DEFAULTTONEAREST = 0x2

VK_CODES = {
    "PageDown": 0x22,
    "PageUp": 0x21,
    "Down": 0x28,
    "Up": 0x26,
    "Space": 0x20,
    "Home": 0x24,
    "End": 0x23,
    "Left": 0x25,
    "Right": 0x27,
}
EXTENDED_VK = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28}

DEFAULT_BROWSERS = (
    "chrome.exe",
    "msedge.exe",
    "brave.exe",
    "firefox.exe",
    "opera.exe",
    "vivaldi.exe",
    "yandex.exe",
    "thorium.exe",
)

_IS_WIN = sys.platform == "win32"

if _IS_WIN:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.PostMessageW.restype = wintypes.BOOL
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsWindow.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
    _user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.MonitorFromWindow.restype = wintypes.HMONITOR
    _user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]
    _user32.GetMonitorInfoW.restype = wintypes.BOOL

    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
else:
    _user32 = None
    _kernel32 = None


class ActiveWindowError(RuntimeError):
    pass


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _resolve_vk(name: str) -> int:
    name = (name or "").strip()
    if len(name) == 1:
        return ord(name.upper())
    code = VK_CODES.get(name)
    if code is None:
        raise ActiveWindowError(f"bilinmeyen tuş: {name}")
    return code


def _process_name(pid: int) -> str:
    if not _IS_WIN or not pid:
        return ""
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return os.path.basename(buf.value).lower()
    finally:
        _kernel32.CloseHandle(handle)


def _window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _window_title(hwnd: int) -> str:
    length = _user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    rect = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


def foreground_window() -> int:
    if not _IS_WIN:
        return 0
    return int(_user32.GetForegroundWindow() or 0)


def monitor_index(hwnd: int) -> int | None:
    """Pencerenin ekran sırası (soldan sağa 1'den başlar)."""
    if not _IS_WIN:
        return None
    handle = _user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not handle:
        return None
    for h, idx, _left, _top, _primary in _enumerate_monitors():
        if h == int(handle):
            return idx
    return None


def _enumerate_monitors() -> list[tuple[int, int, int, int, int]]:
    """[(handle, 1-based sıra, sol, üst, birincil), ...] soldan sağa sıralı."""
    if not _IS_WIN:
        return []
    handles: list[int] = []
    CB = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
    )

    def cb(hmon, hdc, rect, lp):
        handles.append(int(hmon))
        return True

    _user32.EnumDisplayMonitors.argtypes = [
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        CB,
        wintypes.LPARAM,
    ]
    _user32.EnumDisplayMonitors.restype = wintypes.BOOL
    _user32.EnumDisplayMonitors(None, None, CB(cb), 0)

    entries = []
    for h in handles:
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not _user32.GetMonitorInfoW(h, ctypes.byref(info)):
            continue
        r = info.rcMonitor
        entries.append((h, r.left, r.top, bool(info.dwFlags & MONITORINFOF_PRIMARY)))
    entries.sort(key=lambda e: (e[1], e[2]))
    return [(h, i + 1, left, top, primary) for i, (h, left, top, primary) in enumerate(entries)]


def monitor_label(hwnd: int) -> str:
    idx = monitor_index(hwnd)
    return f"ekran {idx}" if idx else "ekran ?"


class ActiveWindowScroller:
    """Odaktaki ya da seçilen ekrandaki tarayıcı penceresine tuş gönderir.

    Ayrı Chrome profili/sekmesi açmaz ve odağı çalmaz: tuşlar doğrudan
    hedef pencereye `PostMessage` ile yollanır. Bu sayede ikinci monitörde
    çalışan sayfa, ön planda olmasa bile kaydırılır.
    """

    name = "active"

    def __init__(
        self,
        scroll_down_key: str = "PageDown",
        scroll_up_key: str = "PageUp",
        allowed_processes: list[str] | tuple[str, ...] | None = None,
        target_monitor: int = 0,
        prefer_foreground: bool = True,
        use_wheel: bool = False,
        wheel_notches: int = 3,
    ):
        if not _IS_WIN:
            raise ActiveWindowError("aktif pencere modu yalnızca Windows'ta çalışır")
        self.scroll_down_key = scroll_down_key
        self.scroll_up_key = scroll_up_key
        self._down_vk = _resolve_vk(scroll_down_key)
        self._up_vk = _resolve_vk(scroll_up_key)
        self._own_pid = os.getpid()
        allowed = allowed_processes or DEFAULT_BROWSERS
        self._allowed = {str(p).lower() for p in allowed if p}
        self.target_monitor = int(target_monitor or 0)
        self.prefer_foreground = bool(prefer_foreground)
        self.use_wheel = bool(use_wheel)
        self.wheel_notches = max(1, int(wheel_notches))
        self.note = ""
        self.last_scroll_method: str | None = None
        self._cached = 0

    @property
    def url(self) -> str:
        hwnd = self._cached or foreground_window()
        if not hwnd:
            return ""
        return _window_title(hwnd)

    def _browser_windows(self) -> list[tuple[int, str, int]]:
        found: list[tuple[int, str, int]] = []
        CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, lp):
            if not _user32.IsWindowVisible(hwnd) or _user32.IsIconic(hwnd):
                return True
            if not _window_title(hwnd):
                return True
            rect = _window_rect(hwnd)
            if not rect or rect[2] < 200 or rect[3] < 120:
                return True
            pid = _window_pid(hwnd)
            if pid == self._own_pid:
                return True
            name = _process_name(pid)
            if name not in self._allowed:
                return True
            found.append((hwnd, name, _monitor_id(hwnd)))
            return True

        _user32.EnumWindows.argtypes = [CB, wintypes.LPARAM]
        _user32.EnumWindows.restype = wintypes.BOOL
        _user32.EnumWindows(CB(cb), 0)
        return found

    def pick(self) -> tuple[int, str] | None:
        candidates = self._browser_windows()
        if not candidates:
            self.note = "tarayıcı penceresi bulunamadı"
            return None

        fg = foreground_window()
        if fg:
            name = _process_name(_window_pid(fg))
            if name in self._allowed and _user32.IsWindowVisible(fg):
                if not self.target_monitor or _monitor_id(fg) == self.target_monitor:
                    self.note = _window_title(fg)[:40]
                    return fg, name

        if self.target_monitor:
            matched = [c for c in candidates if c[2] == self.target_monitor]
            if matched:
                hwnd, name, _ = matched[0]
                self.note = _window_title(hwnd)[:40]
                return hwnd, name
            self.note = f"ekran {self.target_monitor}'de tarayıcı yok"
            return None

        hwnd, name, _ = candidates[0]
        self.note = _window_title(hwnd)[:40]
        return hwnd, name

    def target(self) -> tuple[int, str] | None:
        found = self.pick()
        if found is not None:
            self._cached = found[0]
        return found

    def focus(self) -> None:
        self.target()

    def _post_key(self, hwnd: int, vk: int) -> bool:
        scan = _user32.MapVirtualKeyW(vk, 0)
        extended = 1 if vk in EXTENDED_VK else 0
        lparam_down = 1 | (scan << 16) | (extended << 24)
        lparam_up = lparam_down | (1 << 30) | (1 << 31)
        ok_down = _user32.PostMessageW(hwnd, WM_KEYDOWN, vk, lparam_down)
        time.sleep(0.01)
        ok_up = _user32.PostMessageW(hwnd, WM_KEYUP, vk, lparam_up)
        return bool(ok_down and ok_up)

    def _post_wheel(self, hwnd: int, notches: int) -> bool:
        rect = _window_rect(hwnd)
        if not rect:
            return False
        x = rect[0] + rect[2] // 2
        y = rect[1] + rect[3] // 2
        delta = (WHEEL_DELTA * max(-8, min(8, notches))) & 0xFFFF
        wparam = delta << 16
        lparam = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
        return bool(_user32.PostMessageW(hwnd, WM_MOUSEWHEEL, wparam, lparam))

    def _scroll(self, vk: int, notches: int) -> str:
        found = self.target()
        if found is None:
            return "none"
        hwnd, _ = found
        if not _user32.IsWindow(hwnd):
            self.note = "pencere kayboldu"
            return "none"

        if self.use_wheel:
            self._post_wheel(hwnd, notches)
        self._post_key(hwnd, vk)
        return "key+wheel" if self.use_wheel else "key"

    def scroll(self, direction: str) -> str:
        if direction == "SCROLL_UP":
            self.last_scroll_method = self._scroll(self._up_vk, -self.wheel_notches)
        else:
            self.last_scroll_method = self._scroll(self._down_vk, self.wheel_notches)
        return self.last_scroll_method

    def close(self) -> None:
        pass

    def __enter__(self) -> "ActiveWindowScroller":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def _monitor_id(hwnd: int) -> int:
    return monitor_index(hwnd) or 0
