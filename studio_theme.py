"""Theme palettes, dynamic color engine, typography and semantic log highlighter."""
from __future__ import annotations

from pathlib import Path
import re
import sys

from PySide6.QtCore import QEasingCurve, QPointF
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QApplication


COLOR_PRESETS: tuple[tuple[str, str], ...] = (
    ("#4F8BFF", "钴蓝星尘"),
    ("#C54A3E", "红金铁冠"),
    ("#D99B26", "古金琥珀"),
    ("#22B573", "深海翡翠"),
    ("#8B5CF6", "秘境紫罗兰"),
)


def motion_duration(milliseconds: int) -> int:
    if sys.platform == "win32":
        try:
            import ctypes
            enabled = ctypes.c_int(1)
            if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0) and not enabled.value:
                return 0
        except (OSError, AttributeError, ValueError):
            pass
    return milliseconds


def studio_font(size: float = 10.0, weight=None) -> QFont:
    font = QFont()
    font.setFamilies(["Segoe UI", "Microsoft YaHei UI", "Noto Sans CJK SC"])
    font.setPointSizeF(size)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    if weight is not None:
        font.setWeight(weight)
    return font


def with_alpha(color: str | QColor, alpha: int) -> QColor:
    result = QColor(color)
    result.setAlpha(max(0, min(255, alpha)))
    return result


def mac_curve() -> QEasingCurve:
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(QPointF(.22, 1.0), QPointF(.36, 1.0), QPointF(1.0, 1.0))
    return curve


def blend(a: QColor, b: QColor, ratio: float) -> QColor:
    ratio = min(1.0, max(0.0, ratio))
    return QColor(
        round(a.red() * (1 - ratio) + b.red() * ratio),
        round(a.green() * (1 - ratio) + b.green() * ratio),
        round(a.blue() * (1 - ratio) + b.blue() * ratio),
    )


def _hsv_hex(h: float, s: float, v: float) -> str:
    return QColor.fromHsvF(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v))).name().upper()


def is_warm_accent(accent_hex: str) -> bool:
    col = QColor(accent_hex)
    if not col.isValid():
        return False
    hue = col.hsvHueF()
    sat = col.hsvSaturationF()
    if hue < 0 or sat < 0.18:
        return False
    deg = hue * 360.0
    return deg <= 62.0 or deg >= 312.0


PALETTES = {
    "light": {
        "background": "#F3F5FC", "background2": "#E8EFFB",
        "ink": "#1E2438", "muted": "#62708B", "accent": "#5965E9",
        "accent_hover": "#7480F7", "accent_soft": "#EBEEFF",
        "card": "#FFFFFF", "card_line": "#DFE5F0",
        "label": "#3E4B66", "caption": "#707D98", "input": "#FBFCFF",
        "row": "#F5F7FC", "row_active": "#EDF0FF",
        "row_active_line": "#B8C3FF", "subtle": "#F7F9FD",
        "subtle_line": "#E4EAF4", "btn": "#ECEFF8",
        "btn_hover": "#E0E6F8", "btn_text": "#39435F",
        "danger": "#FFF0F0", "danger_hover": "#FFE0E0",
        "danger_text": "#B75252", "disabled": "#E9ECF3",
        "disabled_text": "#A1ABC0", "scroll": "#CBD4E5",
        "highlight": "#C5CEFF", "glow_a": "#B6CEFF",
        "glow_b": "#E0CDFF", "glow_c": "#A4E6DB", "nav_tint": "#EAE4F5",
    },
    "dark": {
        "background": "#0E1422", "background2": "#162033",
        "ink": "#F2F5FF", "muted": "#A2AFC8", "accent": "#4F8BFF",
        "accent_hover": "#6FA2FF", "accent_soft": "#24324D",
        "card": "#1A2336", "card_line": "#34435E",
        "label": "#DCE4F7", "caption": "#9BAAC8", "input": "#1E283D",
        "row": "#1F2A40", "row_active": "#2B3A5E",
        "row_active_line": "#6C9BFF", "subtle": "#1A2438",
        "subtle_line": "#31405B", "btn": "#28354F",
        "btn_hover": "#344466", "btn_text": "#EBF0FF",
        "danger": "#482A39", "danger_hover": "#674052",
        "danger_text": "#FFD2D9", "disabled": "#242F44",
        "disabled_text": "#74819B", "scroll": "#52617C",
        "highlight": "#4E68A6", "glow_a": "#4E68B8",
        "glow_b": "#734D8D", "glow_c": "#266D7A", "nav_tint": "#2A1B38",
    },
    "dark_glass": {
        "background": "#0D0909", "background2": "#221310",
        "ink": "#F9F0E3", "muted": "#C9AD96", "accent": "#C54A3E",
        "accent_hover": "#D9634F", "accent_soft": "#3F2421",
        "card": "#211816", "card_line": "#694B37",
        "label": "#EFE0CE", "caption": "#BD9D82", "input": "#2B1F1C",
        "row": "#281C1A", "row_active": "#48231F",
        "row_active_line": "#AD7451", "subtle": "#241A18",
        "subtle_line": "#5A3B31", "btn": "#392723",
        "btn_hover": "#56352C", "btn_text": "#F8E7D4",
        "danger": "#502322", "danger_hover": "#68302A",
        "danger_text": "#FFD2C5", "disabled": "#332825",
        "disabled_text": "#8D796B", "scroll": "#7A5141",
        "highlight": "#886343", "glow_a": "#C82427",
        "glow_b": "#D6A451", "glow_c": "#793117", "nav_tint": "#2E151B",
    },
    "light_glass": {
        "background": "#F8F4EE", "background2": "#EFE4D5",
        "ink": "#392824", "muted": "#78665B", "accent": "#A23B36",
        "accent_hover": "#BE5548", "accent_soft": "#F6E6DF",
        "card": "#FFF9F1", "card_line": "#E1CDB9",
        "label": "#5E463B", "caption": "#876D60", "input": "#FFFCF8",
        "row": "#F8EFE6", "row_active": "#F5E3D7",
        "row_active_line": "#CCA384", "subtle": "#FDF5EB",
        "subtle_line": "#EAD6C1", "btn": "#F1E6DA",
        "btn_hover": "#E7D5C5", "btn_text": "#584238",
        "danger": "#FAE5E1", "danger_hover": "#F5D2CD",
        "danger_text": "#A03D37", "disabled": "#F0E8E0",
        "disabled_text": "#AC9487", "scroll": "#D0B29A",
        "highlight": "#F0C5A4", "glow_a": "#C97565",
        "glow_b": "#DDB77D", "glow_c": "#D9B6A5", "nav_tint": "#EFE2D7",
    },
}

LIBRARY_CAPSULE_COLORS = {
    "light": {
        "stat_bg": "#F1E8DC", "stat_line": "#DCC7A9", "stat_ink": "#765733",
        "check_bg": "#DDEFE6", "check_hover": "#C9E6D7", "check_ink": "#25644B", "check_line": "#A3CEBA",
        "exclude_bg": "#F5E8DB", "exclude_hover": "#EFD9C6", "exclude_ink": "#8B5535", "exclude_line": "#D9B495",
        "clear_bg": "#F9E1E2", "clear_hover": "#F2CCCE", "clear_ink": "#9A3E47", "clear_line": "#DAA1A8",
    },
    "dark": {
        "stat_bg": "#303B4D", "stat_line": "#58647A", "stat_ink": "#E6C68E",
        "check_bg": "#27463F", "check_hover": "#365B50", "check_ink": "#C7E9D6", "check_line": "#567D6F",
        "exclude_bg": "#48372F", "exclude_hover": "#604538", "exclude_ink": "#EED1AD", "exclude_line": "#80604B",
        "clear_bg": "#4B2D35", "clear_hover": "#67404A", "clear_ink": "#F1B7BC", "clear_line": "#885665",
    },
    "light_glass": {
        "stat_bg": "#F2E6D6", "stat_line": "#D9BA91", "stat_ink": "#805A2C",
        "check_bg": "#E1EDE0", "check_hover": "#D0E4D2", "check_ink": "#326C4A", "check_line": "#AEC8AA",
        "exclude_bg": "#F5E6D8", "exclude_hover": "#EDD6C1", "exclude_ink": "#8C542C", "exclude_line": "#D6B392",
        "clear_bg": "#F8E2DE", "clear_hover": "#EFCDC7", "clear_ink": "#9A443C", "clear_line": "#D8A39B",
    },
    "dark_glass": {
        "stat_bg": "#463024", "stat_line": "#826145", "stat_ink": "#E6C28C",
        "check_bg": "#2C4032", "check_hover": "#3B5541", "check_ink": "#CFE6B7", "check_line": "#5D7A57",
        "exclude_bg": "#4C3225", "exclude_hover": "#62412E", "exclude_ink": "#EAC6A1", "exclude_line": "#855D41",
        "clear_bg": "#512726", "clear_hover": "#71352F", "clear_ink": "#F6BBB0", "clear_line": "#93524A",
    },
}
for _p_name, _cap in LIBRARY_CAPSULE_COLORS.items():
    for _r, _col in _cap.items():
        PALETTES[_p_name][f"library_{_r}"] = _col

LOG_PALETTES = {
    "light": dict(log_text="#384760", log_muted="#7A889E", log_success="#158058",
                  log_warning="#B4690E", log_error="#C83745", log_info="#3B5BDB", log_link="#1D70B8"),
    "dark": dict(log_text="#C9D4E9", log_muted="#7E91B1", log_success="#4ADE80",
                 log_warning="#FBBF24", log_error="#F87171", log_info="#60A5FA", log_link="#38BDF8"),
    "light_glass": dict(log_text="#5B483D", log_muted="#947E6E", log_success="#257953",
                        log_warning="#B06512", log_error="#B83333", log_info="#964336", log_link="#6E4E9E"),
    "dark_glass": dict(log_text="#E2CEB8", log_muted="#9D8270", log_success="#6EE7B7",
                       log_warning="#FCD34D", log_error="#FB7185", log_info="#FDBA74", log_link="#7DD3FC"),
}
for _p_name, _log_col in LOG_PALETTES.items():
    PALETTES[_p_name].update(_log_col)


def build_dynamic_palette(theme: str, material: str, accent_hex: str) -> dict[str, str]:
    """Derive a complete readable palette from any user-selected accent color."""
    warm = is_warm_accent(accent_hex)
    base_key = f"{theme}_glass" if (material == "liquid" or warm) else theme
    pal = dict(PALETTES[base_key])

    col = QColor(accent_hex)
    if not col.isValid():
        return pal

    h = max(0.0, col.hsvHueF())
    s = col.hsvSaturationF()
    v = col.valueF()
    is_dark = (theme == "dark")

    # 保证主色按钮上的白字在浅色/深色模式下都有充足对比度
    btn_v = max(0.55, v) if is_dark else min(0.70, max(0.36, v))
    btn_s = max(0.18, s) if s > 0.05 else 0.05
    acc = QColor.fromHsvF(h, btn_s, btn_v)
    acc_hover = QColor.fromHsvF(h, max(0.0, btn_s * 0.88), min(1.0, btn_v + 0.12))

    pal["accent"] = acc.name().upper()
    pal["accent_hover"] = acc_hover.name().upper()
    pal["accent_soft"] = _hsv_hex(h, min(0.55, btn_s * 0.58), 0.25 if is_dark else 0.94)
    pal["row_active_line"] = _hsv_hex(h, min(0.78, btn_s * 0.85), 0.82 if is_dark else 0.72)
    pal["highlight"] = _hsv_hex(h, min(0.60, btn_s * 0.68), 0.55 if is_dark else 0.88)

    # 极光流光：暖色自动配古金 (38°)，冷色自动配相邻梦幻紫/青
    h_b = 0.105 if (h <= 0.12 or h >= 0.88) else ((h + 0.11) % 1.0)
    h_c = (h - 0.11) % 1.0
    pal["glow_a"] = _hsv_hex(h, min(0.95, max(0.45, btn_s)), 0.78 if is_dark else 0.86)
    pal["glow_b"] = _hsv_hex(h_b, min(0.85, max(0.35, btn_s * 0.85)), 0.76 if is_dark else 0.88)
    pal["glow_c"] = _hsv_hex(h_c, min(0.80, max(0.35, btn_s * 0.78)), 0.52 if is_dark else 0.85)
    pal["nav_tint"] = _hsv_hex(h, min(0.50, btn_s * 0.58), 0.16 if is_dark else 0.93)

    if material == "liquid":
        # 液体玻璃下让基底与卡片微微染上所选主色调，保留 Darkest Dungeon 黑曜石质感
        if is_dark:
            pal["background"] = _hsv_hex(h, min(0.38, btn_s * 0.40), 0.065)
            pal["background2"] = _hsv_hex(h, min(0.48, btn_s * 0.52), 0.14)
            pal["card"] = _hsv_hex(h, min(0.34, btn_s * 0.36), 0.135)
            pal["card_line"] = _hsv_hex(h, min(0.48, btn_s * 0.50), 0.38)
            pal["input"] = _hsv_hex(h, min(0.34, btn_s * 0.36), 0.17)
            pal["subtle"] = _hsv_hex(h, min(0.32, btn_s * 0.35), 0.15)
            pal["row"] = _hsv_hex(h, min(0.32, btn_s * 0.35), 0.165)
            pal["row_active"] = _hsv_hex(h, min(0.55, btn_s * 0.62), 0.27)
            pal["btn"] = _hsv_hex(h, min(0.35, btn_s * 0.38), 0.22)
            pal["btn_hover"] = _hsv_hex(h, min(0.42, btn_s * 0.45), 0.31)
        else:
            pal["background"] = _hsv_hex(h, min(0.08, btn_s * 0.10), 0.975)
            pal["background2"] = _hsv_hex(h, min(0.14, btn_s * 0.16), 0.935)
            pal["card"] = _hsv_hex(h, min(0.05, btn_s * 0.07), 0.992)
            pal["card_line"] = _hsv_hex(h, min(0.24, btn_s * 0.28), 0.87)
            pal["row_active"] = _hsv_hex(h, min(0.18, btn_s * 0.22), 0.94)
    return pal


def current_colors() -> dict[str, str]:
    app = QApplication.instance()
    if app is not None:
        selected = app.property("studio_colors")
        if isinstance(selected, dict):
            return selected
    return PALETTES["dark"]


def find_asset_file(filename: str) -> Path | None:
    folders = [Path(__file__).resolve().parent]
    if getattr(sys, "frozen", False):
        folders.insert(0, Path(sys.executable).resolve().parent)
    folders.append(Path.cwd())
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        folders.append(Path(bundled))
    seen = set()
    for folder in folders:
        path = folder / filename
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            return path
    return None


def find_brand_image(prefer: str = "blue") -> Path | None:
    """Resolve blue.png / red.png based on active hue (never uses mod.ico)."""
    names = ("red.png", "blue.png", "1.png") if prefer == "red" else ("blue.png", "red.png", "1.png")
    for name in names:
        if (found := find_asset_file(name)) is not None:
            return found
    return None


def classify_log_role(line: str) -> str:
    low = line.casefold().strip()
    if not low:
        return "muted"
    if any(w in low for w in ("unhandled error", "failed", "error", "✕", "失败", "异常", "超限", "缺少", "无效", "拒绝", "找不到")):
        return "error"
    if any(w in low for w in ("warning", "unconfirmed", "check log", "跳过", "警告", "未确认", "待核实", "注意", "接近", "已排除", "已清除", "停止")):
        return "warning"
    if any(w in low for w in ("success", "submitted.", "complete", "✓", "成功", "已完成", "已确认完成", "已就绪", "清理完成", "扫描完成", "添加完成")):
        return "success"
    if low.startswith(("[", "━━")) or any(w in low for w in ("开始", "已勾选", "已生成", "正在", "归档")):
        return "info"
    return "text"


class SemanticLogHighlighter(QSyntaxHighlighter):
    TIMESTAMP = re.compile(r"\b(?:\d{4}-\d\d-\d\d[ T])?\d\d:\d\d(?::\d\d)?\b")
    URL = re.compile(r"https?://\S+", re.I)
    WORKSHOP_ID = re.compile(r"\b(?:Workshop ID|工坊 ID|ManifestID)[:\s]*\d{7,20}\b", re.I)
    BRACKET_TAG = re.compile(r"\[\d+/\d+\]")
    WIN_PATH = re.compile(r"[A-Za-z]:\\[^\s\r\n]+")

    def __init__(self, document, colors: dict[str, str]):
        super().__init__(document)
        self.colors = colors
        self._formats = {}
        self._configure()

    def _configure(self):
        self._formats = {}
        for role in ("text", "muted", "success", "warning", "error", "info", "link"):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(self.colors[f"log_{role}"]))
            if role in ("error", "success", "warning", "info"):
                fmt.setFontWeight(QFont.Weight.DemiBold)
            self._formats[role] = fmt

    def set_colors(self, colors):
        if self.colors == colors:
            return
        self.colors = colors
        self._configure()
        self.rehighlight()

    def highlightBlock(self, line: str):
        role = classify_log_role(line)
        self.setFormat(0, len(line), self._formats[role])
        for m in self.TIMESTAMP.finditer(line):
            self.setFormat(m.start(), len(m.group()), self._formats["muted"])
        for m in self.BRACKET_TAG.finditer(line):
            self.setFormat(m.start(), len(m.group()), self._formats["info"])
        for m in self.WIN_PATH.finditer(line):
            self.setFormat(m.start(), len(m.group()), self._formats["muted"])
        for m in self.WORKSHOP_ID.finditer(line):
            self.setFormat(m.start(), len(m.group()), self._formats["info"])
        for m in self.URL.finditer(line):
            self.setFormat(m.start(), len(m.group()), self._formats["link"])