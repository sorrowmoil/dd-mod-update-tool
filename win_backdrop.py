"""Win10 / Win11 native frosted glass & borderless DWM frame helper (pure ctypes)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import QWidget

IS_WIN32 = sys.platform == "win32"

WM_ERASEBKGND = 0x0014
WM_GETMINMAXINFO = 0x0024
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCPAINT = 0x0085
WM_NCACTIVATE = 0x0086
WM_ENTERSIZEMOVE = 0x0231
WM_EXITSIZEMOVE = 0x0232

HTCLIENT, HTCAPTION = 1, 2
HTLEFT, HTRIGHT, HTTOP = 10, 11, 12
HTTOPLEFT, HTTOPRIGHT = 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17

GWL_STYLE = -16
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000

SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_FRAMECHANGED = 0x0001, 0x0002, 0x0004, 0x0020
SM_CXSIZEFRAME, SM_CYSIZEFRAME, SM_CXPADDEDBORDER = 32, 33, 92
MONITOR_DEFAULTTONEAREST = 2

WCA_ACCENT_POLICY = 19
ACCENT_DISABLED = 0
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", POINT), ("ptMaxSize", POINT), ("ptMaxPosition", POINT),
        ("ptMinTrackSize", POINT), ("ptMaxTrackSize", POINT),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
    ]


class MARGINS(ctypes.Structure):
    _fields_ = [("cxLeftWidth", ctypes.c_int), ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int), ("cyBottomHeight", ctypes.c_int)]


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_uint), ("AccentFlags", ctypes.c_uint),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_uint)]


class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_uint), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_size_t)]


class WTA_OPTIONS(ctypes.Structure):
    _fields_ = [("dwFlags", wintypes.DWORD), ("dwMask", wintypes.DWORD)]


def win_build() -> int:
    if not IS_WIN32: return 0
    try: return sys.getwindowsversion().build
    except (AttributeError, OSError): return 0

def backdrop_supported() -> bool: return IS_WIN32 and win_build() >= 17134
def mica_supported() -> bool: return IS_WIN32 and win_build() >= 22621

def _get_dpi_for_hwnd(hwnd: int) -> int:
    try:
        fn = ctypes.windll.user32.GetDpiForWindow
        fn.argtypes, fn.restype = [wintypes.HWND], wintypes.UINT
        dpi = fn(wintypes.HWND(hwnd))
        return dpi if dpi > 0 else 96
    except (AttributeError, OSError): return 96

def _resize_border_px(hwnd: int) -> tuple[int, int]:
    u32 = ctypes.windll.user32; dpi = _get_dpi_for_hwnd(hwnd)
    try:
        fn = u32.GetSystemMetricsForDpi
        fn.argtypes, fn.restype = [ctypes.c_int, wintypes.UINT], ctypes.c_int
        return fn(SM_CXSIZEFRAME, dpi) + fn(SM_CXPADDEDBORDER, dpi), fn(SM_CYSIZEFRAME, dpi) + fn(SM_CXPADDEDBORDER, dpi)
    except (AttributeError, OSError):
        return (u32.GetSystemMetrics(SM_CXSIZEFRAME) + u32.GetSystemMetrics(SM_CXPADDEDBORDER),
                u32.GetSystemMetrics(SM_CYSIZEFRAME) + u32.GetSystemMetrics(SM_CXPADDEDBORDER))

def setup_dwm_frameless_window(window: QWidget) -> None:
    if not IS_WIN32: return
    hwnd = int(window.winId()); u32 = ctypes.windll.user32
    get_long = getattr(u32, "GetWindowLongPtrW", u32.GetWindowLongW)
    set_long = getattr(u32, "SetWindowLongPtrW", u32.SetWindowLongW)
    get_long.argtypes, get_long.restype = [wintypes.HWND, ctypes.c_int], ctypes.c_ssize_t
    set_long.argtypes, set_long.restype = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t], ctypes.c_ssize_t

    style = get_long(wintypes.HWND(hwnd), GWL_STYLE)
    style = (style | WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU) & ~WS_POPUP
    set_long(wintypes.HWND(hwnd), GWL_STYLE, style)

    try:
        uxt = ctypes.windll.uxtheme
        uxt.SetWindowThemeAttribute.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.POINTER(WTA_OPTIONS), wintypes.DWORD]
        uxt.SetWindowThemeAttribute.restype = ctypes.c_long
        opt = WTA_OPTIONS(0x0F, 0x0F)
        uxt.SetWindowThemeAttribute(wintypes.HWND(hwnd), 1, ctypes.byref(opt), ctypes.sizeof(opt))
    except (AttributeError, OSError): pass

    u32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    u32.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)

    dwm_extend = ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea
    dwm_extend.argtypes, dwm_extend.restype = [wintypes.HWND, ctypes.POINTER(MARGINS)], ctypes.c_long
    margins = MARGINS(-1, -1, -1, -1)
    dwm_extend(wintypes.HWND(hwnd), ctypes.byref(margins))

def set_dwm_attribute(window: QWidget, attribute: int, value: int) -> bool:
    if not IS_WIN32: return False
    try:
        fn = ctypes.windll.dwmapi.DwmSetWindowAttribute
        fn.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        fn.restype = ctypes.c_long
        data = ctypes.c_int(value)
        return fn(wintypes.HWND(int(window.winId())), wintypes.DWORD(attribute), ctypes.byref(data), ctypes.sizeof(data)) == 0
    except (OSError, AttributeError, TypeError, ValueError): return False

def _set_win10_composition(hwnd: int, state: int, tint: QColor | None = None) -> bool:
    try:
        fn = ctypes.windll.user32.SetWindowCompositionAttribute
        fn.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA)]
        fn.restype = wintypes.BOOL
    except (AttributeError, OSError): return False

    abgr, flags = 0, 0
    if tint is not None and state == ACCENT_ENABLE_ACRYLICBLURBEHIND:
        a = max(1, tint.alpha())
        abgr = (a << 24) | (tint.blue() << 16) | (tint.green() << 8) | tint.red()
        flags = 2
    policy = ACCENT_POLICY(state, flags, abgr, 0)
    data = WINDOWCOMPOSITIONATTRIBDATA(WCA_ACCENT_POLICY, ctypes.cast(ctypes.byref(policy), ctypes.c_void_p), ctypes.sizeof(policy))
    return bool(fn(wintypes.HWND(hwnd), ctypes.byref(data)))

def apply_desktop_backdrop(window: QWidget, *, enabled: bool, mode: str, dark: bool, tint: QColor, dragging: bool = False) -> str:
    if not IS_WIN32: return "none"
    state_sig = (bool(enabled), str(mode), bool(dark), tint.rgba(), bool(dragging))
    if getattr(window, "_last_backdrop_sig", None) == state_sig:
        return getattr(window, "_last_backdrop_kind", "none")
    hwnd = int(window.winId()); build = win_build()

    if build >= 22000:
        set_dwm_attribute(window, 20, 1 if dark else 0)
        set_dwm_attribute(window, 33, 2)

    def _finish(kind: str) -> str:
        window._last_backdrop_sig = state_sig
        window._last_backdrop_kind = kind
        return kind

    if not enabled:
        if build >= 22621: set_dwm_attribute(window, 38, 1)
        _set_win10_composition(hwnd, ACCENT_DISABLED)
        return _finish("none")

    if build >= 22621:
        _set_win10_composition(hwnd, ACCENT_DISABLED)
        want_acrylic = (mode == "acrylic")
        if set_dwm_attribute(window, 38, 3 if want_acrylic else 2):
            return _finish("acrylic" if want_acrylic else "mica")

    if build >= 17134:
        if dragging:
            if _set_win10_composition(hwnd, ACCENT_ENABLE_BLURBEHIND): return _finish("aero_drag")
            return _finish("none")
        if _set_win10_composition(hwnd, ACCENT_ENABLE_ACRYLICBLURBEHIND, tint):
            return _finish("acrylic")

    return _finish("none")

def handle_frameless_native_event(window: QWidget, event_type, message, *, titlebar_height: int = 46, on_drag_state_changed=None) -> tuple[bool, int] | None:
    if not IS_WIN32 or bytes(event_type) != b"windows_generic_MSG": return None
    msg = wintypes.MSG.from_address(int(message))
    hwnd = int(msg.hWnd or 0)
    if not hwnd: return None
    u32 = ctypes.windll.user32
    u32.IsZoomed.argtypes, u32.IsZoomed.restype = [wintypes.HWND], wintypes.BOOL

    if msg.message == WM_ERASEBKGND:
        return True, 1
    if msg.message == WM_NCPAINT:
        return True, 0
    if msg.message == WM_NCACTIVATE:
        return True, 1

    if msg.message == WM_GETMINMAXINFO:
        u32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        u32.MonitorFromWindow.restype = wintypes.HMONITOR
        u32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
        u32.GetMonitorInfoW.restype = wintypes.BOOL
        hmon = u32.MonitorFromWindow(wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST)
        if hmon:
            mi = MONITORINFO(); mi.cbSize = ctypes.sizeof(MONITORINFO)
            if u32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                mmi = MINMAXINFO.from_address(int(msg.lParam))
                mmi.ptMaxPosition.x = abs(mi.rcWork.left - mi.rcMonitor.left)
                mmi.ptMaxPosition.y = abs(mi.rcWork.top - mi.rcMonitor.top)
                mmi.ptMaxSize.x = abs(mi.rcWork.right - mi.rcWork.left)
                mmi.ptMaxSize.y = abs(mi.rcWork.bottom - mi.rcWork.top)
                return True, 0

    if msg.message == WM_ENTERSIZEMOVE and on_drag_state_changed:
        on_drag_state_changed(True); return None
    if msg.message == WM_EXITSIZEMOVE and on_drag_state_changed:
        on_drag_state_changed(False); return None

    if msg.message == WM_NCCALCSIZE:
        if msg.wParam:
            if u32.IsZoomed(wintypes.HWND(hwnd)):
                bx, by = _resize_border_px(hwnd)
                params = NCCALCSIZE_PARAMS.from_address(int(msg.lParam))
                params.rgrc[0].left += bx; params.rgrc[0].right -= bx
                params.rgrc[0].top += by; params.rgrc[0].bottom -= by
            return True, 0
        return True, 0

    if msg.message == WM_NCHITTEST:
        rect = wintypes.RECT()
        u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
        x = ctypes.c_short(msg.lParam & 0xFFFF).value
        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value

        if not u32.IsZoomed(wintypes.HWND(hwnd)):
            border = max(5, round(6 * _get_dpi_for_hwnd(hwnd) / 96.0))
            left, right = x < rect.left + border, x >= rect.right - border
            top, bottom = y < rect.top + border, y >= rect.bottom - border
            if top and left: return True, HTTOPLEFT
            if top and right: return True, HTTOPRIGHT
            if bottom and left: return True, HTBOTTOMLEFT
            if bottom and right: return True, HTBOTTOMRIGHT
            if left: return True, HTLEFT
            if right: return True, HTRIGHT
            if top: return True, HTTOP
            if bottom: return True, HTBOTTOM

        local_pos: QPoint = window.mapFromGlobal(QCursor.pos())
        if 0 <= local_pos.y() <= titlebar_height:
            child = window.childAt(local_pos)
            interactive = False
            cur = child
            while cur is not None and cur is not window:
                if cur.focusPolicy() != Qt.FocusPolicy.NoFocus or cur.objectName() == "captionBtn":
                    interactive = True; break
                cur = cur.parentWidget()
            if not interactive: return True, HTCAPTION

        return True, HTCLIENT

    return None