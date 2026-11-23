"""Custom Qt-painted widgets & frosted-glass surfaces for DD Workshop Studio."""
from __future__ import annotations
import math
from pathlib import Path
from PySide6.QtCore import Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImageReader, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication, QColorDialog, QDialog, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QSlider, QVBoxLayout, QWidget
from studio_theme import blend, current_colors, mac_curve, motion_duration, studio_font, with_alpha

class BrandMark(QWidget):
    def __init__(self, image_path: Path | None, size_px: int = 34, parent=None):
        super().__init__(parent); self.setFixedSize(size_px, size_px); self.setAccessibleName("moil的mod上传器标识")
        self._pixmap = QPixmap(str(image_path)) if image_path else QPixmap()

    def paintEvent(self, event):
        c = current_colors(); p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1); path = QPainterPath(); r = max(7.0, rect.width() * 0.22); path.addRoundedRect(rect, r, r); p.setClipPath(path)
        if not self._pixmap.isNull():
            px = self._pixmap; crop = min(px.width(), px.height())
            p.drawPixmap(rect, px, QRectF((px.width() - crop) / 2, (px.height() - crop) / 2, crop, crop))
        else:
            p.fillPath(path, QColor(c["accent_soft"])); p.setPen(QColor(c["accent"])); p.setFont(studio_font(11.0, QFont.Weight.Bold)); p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "DD")
        p.setClipping(False); p.setPen(QPen(QColor(c["row_active_line"]), 1.1)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawRoundedRect(rect, r, r)

class CaptionButton(QWidget):
    clicked = Signal()
    def __init__(self, kind: str, parent=None):
        super().__init__(parent); self.kind = kind; self._hover = self._pressed = self._maximized = False
        self.setObjectName("captionBtn"); self.setFixedSize(40, 30); self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_maximized(self, maximized: bool):
        if self._maximized != bool(maximized): self._maximized = bool(maximized); self.update()
    def enterEvent(self, event): self._hover = True; self.update(); super().enterEvent(event)
    def leaveEvent(self, event): self._hover = self._pressed = False; self.update(); super().leaveEvent(event)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self._pressed = True; self.update(); event.accept(); return
        super().mousePressEvent(event)
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            fire = self._pressed and self.rect().contains(event.position().toPoint()); self._pressed = False; self.update()
            if fire: self.clicked.emit()
            event.accept(); return
        super().mouseReleaseEvent(event)
    def paintEvent(self, event):
        c = current_colors(); p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover or self._pressed:
            bg = QColor("#C63D3D" if self._pressed else "#DC4B4B") if self.kind == "close" else with_alpha(c["ink"], 36 if self._pressed else 20)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(bg); p.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 7, 7)
        fg = QColor("#FFFFFF") if (self.kind == "close" and (self._hover or self._pressed)) else QColor(c["ink"])
        p.setPen(QPen(fg, 1.35)); cx, cy = self.width() / 2, self.height() / 2
        if self.kind == "min": p.drawLine(QPointF(cx - 5, cy), QPointF(cx + 5, cy))
        elif self.kind == "max":
            if self._maximized: p.drawRect(QRectF(cx - 5, cy - 3, 7.5, 7.5)); p.drawLine(QPointF(cx - 2.5, cy - 5), QPointF(cx + 5, cy - 5)); p.drawLine(QPointF(cx + 5, cy - 5), QPointF(cx + 5, cy + 2.5))
            else: p.drawRect(QRectF(cx - 4.5, cy - 4.5, 9, 9))
        else: p.drawLine(QPointF(cx - 4.5, cy - 4.5), QPointF(cx + 4.5, cy + 4.5)); p.drawLine(QPointF(cx + 4.5, cy - 4.5), QPointF(cx - 4.5, cy + 4.5))

class BrandToggleButton(QWidget):
    """Clickable brand crest button with smooth cross-fading red.png / blue.png."""
    clicked = Signal()

    def __init__(self, red_path: Path | None, blue_path: Path | None, initial_warmth: float = 0.0, parent=None):
        super().__init__(parent)
        self.setFixedSize(38, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._hover = self._press = 0.0
        self._down = False
        self._warmth = float(initial_warmth)
        self._pix_red = QPixmap(str(red_path)) if red_path and Path(red_path).is_file() else QPixmap()
        self._pix_blue = QPixmap(str(blue_path)) if blue_path and Path(blue_path).is_file() else QPixmap()
        self._hover_anim = QPropertyAnimation(self, b"hoverLevel", self)
        self._hover_anim.setDuration(motion_duration(170)); self._hover_anim.setEasingCurve(mac_curve())
        self._press_anim = QPropertyAnimation(self, b"pressLevel", self)

    def get_hover(self): return self._hover
    def set_hover(self, v: float): self._hover = max(0.0, min(1.0, float(v))); self.update()
    hoverLevel = Property(float, get_hover, set_hover)

    def get_press(self): return self._press
    def set_press(self, v: float): self._press = max(-0.3, min(1.2, float(v))); self.update()
    pressLevel = Property(float, get_press, set_press)

    def get_warmth(self) -> float: return self._warmth
    def set_warmth(self, v: float): self._warmth = max(0.0, min(1.0, float(v))); self.update()
    warmth = Property(float, get_warmth, set_warmth)

    def enterEvent(self, event):
        self._hover_anim.stop(); self._hover_anim.setStartValue(self._hover); self._hover_anim.setEndValue(1.0); self._hover_anim.start()
        super().enterEvent(event)
    def leaveEvent(self, event):
        self._hover_anim.stop(); self._hover_anim.setStartValue(self._hover); self._hover_anim.setEndValue(0.0); self._hover_anim.start()
        super().leaveEvent(event)

    def _anim_press(self, target: float):
        self._press_anim.stop()
        if target > 0.5:
            self._press_anim.setDuration(motion_duration(80)); self._press_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        else:
            self._press_anim.setDuration(motion_duration(220))
            cb = QEasingCurve(QEasingCurve.Type.OutBack); cb.setOvershoot(1.3); self._press_anim.setEasingCurve(cb)
        self._press_anim.setStartValue(self._press); self._press_anim.setEndValue(target); self._press_anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._down = True; self._anim_press(1.0); event.accept(); return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            fire = self._down and self.rect().contains(event.position().toPoint())
            self._down = False; self._anim_press(0.0)
            if fire: self.clicked.emit()
            event.accept(); return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit(); event.accept(); return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        c = current_colors(); app = QApplication.instance()
        is_dark = (app.property("studio_theme") == "dark") if app else True
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        inset = 1.0 + 1.35 * self._press
        box = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        if self._hover > 0.02:
            bg = QColor(255, 255, 255, round(20 * self._hover)) if is_dark else QColor(0, 0, 0, round(12 * self._hover))
            p.setPen(QPen(with_alpha(c["row_active_line"], round(110 * self._hover)), 1.0))
            p.setBrush(bg); p.drawRoundedRect(box, 9, 9)

        icon_rect = box.adjusted(3.0, 3.0, -3.0, -3.0)
        clip = QPainterPath(); clip.addRoundedRect(icon_rect, 7.0, 7.0); p.setClipPath(clip)

        # ★ 电影级交叉溶解：双色图标随色相流动平滑叠化，零切图顿挫
        has_blue = not self._pix_blue.isNull()
        has_red = not self._pix_red.isNull()
        if has_blue or has_red:
            if has_blue and self._warmth < 0.999:
                p.setOpacity(1.0 - self._warmth)
                p.drawPixmap(icon_rect, self._pix_blue, QRectF(self._pix_blue.rect()))
            if has_red and self._warmth > 0.001:
                p.setOpacity(self._warmth)
                p.drawPixmap(icon_rect, self._pix_red, QRectF(self._pix_red.rect()))
            p.setOpacity(1.0)
        else:
            p.fillPath(clip, QColor(c["accent_soft"]))
            p.setPen(QColor(c["accent"])); p.setFont(studio_font(10.0, QFont.Weight.Bold))
            p.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, "DD")

class NavItemButton(QWidget):
    clicked = Signal()
    def __init__(self, icon_kind: str, text: str, parent=None):
        super().__init__(parent); self.icon_kind, self.label_text = icon_kind, text
        self._active = self._collapsed = False; self._hover = self._active_lvl = 0.0
        self.setFixedHeight(40); self.setCursor(Qt.CursorShape.PointingHandCursor); self.setFocusPolicy(Qt.FocusPolicy.StrongFocus); self.setToolTip(text)
        self._hover_anim = QPropertyAnimation(self, b"hoverLevel", self); self._hover_anim.setDuration(motion_duration(170)); self._hover_anim.setEasingCurve(mac_curve())
        self._active_anim = QPropertyAnimation(self, b"activeLevel", self); self._active_anim.setDuration(motion_duration(220)); self._active_anim.setEasingCurve(mac_curve())

    def get_hover(self): return self._hover
    def set_hover(self, v: float): self._hover = max(0.0, min(1.0, float(v))); self.update()
    hoverLevel = Property(float, get_hover, set_hover)
    def get_active_lvl(self): return self._active_lvl
    def set_active_lvl(self, v: float): self._active_lvl = max(0.0, min(1.0, float(v))); self.update()
    activeLevel = Property(float, get_active_lvl, set_active_lvl)

    def set_active(self, active: bool):
        active = bool(active)
        if self._active == active: return
        self._active = active; target = 1.0 if active else 0.0; self._active_anim.stop()
        if self.isVisible() and motion_duration(220) > 0: self._active_anim.setStartValue(self._active_lvl); self._active_anim.setEndValue(target); self._active_anim.start()
        else: self.set_active_lvl(target)

    def set_collapsed(self, collapsed: bool):
        if self._collapsed != bool(collapsed): self._collapsed = bool(collapsed); self.update()
    def enterEvent(self, event): self._hover_anim.stop(); self._hover_anim.setStartValue(self._hover); self._hover_anim.setEndValue(1.0); self._hover_anim.start(); super().enterEvent(event)
    def leaveEvent(self, event): self._hover_anim.stop(); self._hover_anim.setStartValue(self._hover); self._hover_anim.setEndValue(0.0); self._hover_anim.start(); super().leaveEvent(event)
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()): self.clicked.emit(); event.accept(); return
        super().mouseReleaseEvent(event)
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space): self.clicked.emit(); event.accept(); return
        super().keyPressEvent(event)

    def _draw_icon(self, p: QPainter, cx: float, cy: float, color: QColor):
        p.setPen(QPen(color, 1.55, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)); p.setBrush(Qt.BrushStyle.NoBrush)
        if self.icon_kind == "menu":
            for dy in (-4.5, 0.0, 4.5): p.drawLine(QPointF(cx - 6.5, cy + dy), QPointF(cx + 6.5, cy + dy))
        elif self.icon_kind == "workbench": p.drawRoundedRect(QRectF(cx - 7, cy - 6, 14, 12), 2.5, 2.5); p.drawLine(QPointF(cx - 7, cy - 2), QPointF(cx + 7, cy - 2)); p.drawLine(QPointF(cx - 2.5, cy + 2), QPointF(cx + 2.5, cy + 2))
        elif self.icon_kind == "logs": p.drawRoundedRect(QRectF(cx - 7, cy - 6, 14, 12), 2.5, 2.5); p.drawLine(QPointF(cx - 4, cy - 2), QPointF(cx - 1.5, cy + 0.5)); p.drawLine(QPointF(cx - 1.5, cy + 0.5), QPointF(cx - 4, cy + 3)); p.drawLine(QPointF(cx + 0.5, cy + 3), QPointF(cx + 4.5, cy + 3))
        elif self.icon_kind == "settings": p.drawEllipse(QPointF(cx, cy), 3.0, 3.0); p.drawEllipse(QPointF(cx, cy), 6.5, 6.5)
        elif self.icon_kind == "sort":
            p.drawLine(QPointF(cx - 6.5, cy - 4.5), QPointF(cx + 6.5, cy - 4.5))
            p.drawLine(QPointF(cx - 6.5, cy), QPointF(cx + 2.0, cy))
            p.drawLine(QPointF(cx - 6.5, cy + 4.5), QPointF(cx - 1.5, cy + 4.5))
            p.drawLine(QPointF(cx + 4.5, cy - 1.0), QPointF(cx + 4.5, cy + 5.5))
            p.drawLine(QPointF(cx + 2.2, cy + 3.2), QPointF(cx + 4.5, cy + 5.5))
            p.drawLine(QPointF(cx + 6.8, cy + 3.2), QPointF(cx + 4.5, cy + 5.5))

    def paintEvent(self, event):
        c = current_colors(); p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        app = QApplication.instance(); is_dark = (app.property("studio_theme") == "dark") if app else True
        rect = QRectF(self.rect()).adjusted(2, 1, -2, -1)
        base_a = (20 if is_dark else 14) * self._active_lvl + (11 if is_dark else 8) * self._hover * (1.0 - self._active_lvl)
        if base_a > 0.5: p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(255, 255, 255, round(base_a)) if is_dark else QColor(0, 0, 0, round(base_a))); p.drawRoundedRect(rect, 9, 9)
        fg = blend(QColor(c["label"]), QColor(c["ink"]), self._active_lvl)
        if not self.isEnabled(): fg = QColor(c["disabled_text"])
        self._draw_icon(p, rect.left() + 20, rect.center().y(), fg)
        if not self._collapsed:
            p.setPen(fg); p.setFont(studio_font(10.0, QFont.Weight.DemiBold if self._active_lvl > 0.5 else QFont.Weight.Normal))
            p.drawText(QRectF(rect.left() + 38, rect.top(), rect.width() - 44, rect.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.label_text)

class NavIndicator(QWidget):
    def __init__(self, sidebar: QWidget):
        super().__init__(sidebar); self._target_btn: NavItemButton | None = None; self._cy = self._start_y = self._end_y = -1.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setGeometry(0, 0, 24, sidebar.height()); self._anim = QPropertyAnimation(self, b"centerY", self); self._anim.setDuration(motion_duration(290))
        curve = QEasingCurve(QEasingCurve.Type.OutBack); curve.setOvershoot(0.85); self._anim.setEasingCurve(curve)

    def get_cy(self) -> float: return self._cy
    def set_cy(self, y: float): self._cy = float(y); self.update()
    centerY = Property(float, get_cy, set_cy)

    def track(self, btn: NavItemButton, animated: bool = True):
        self._target_btn = btn; self.setGeometry(0, 0, 24, self.parentWidget().height()); self.raise_()
        if btn.height() <= 0 or btn.y() <= 0: return
        cy = float(btn.geometry().center().y()); self._anim.stop()
        if animated and self._cy >= 0 and self.isVisible() and motion_duration(290) > 0:
            self._start_y, self._end_y = self._cy, cy; self._anim.setStartValue(self._cy); self._anim.setEndValue(cy); self._anim.start()
        else: self._start_y = self._end_y = cy; self.set_cy(cy)

    def snap(self):
        if self._target_btn is not None:
            self.setGeometry(0, 0, 24, self.parentWidget().height()); self.raise_()
            if self._anim.state() != QPropertyAnimation.State.Running and self._target_btn.height() > 0:
                self._cy = float(self._target_btn.geometry().center().y()); self.update()

    def paintEvent(self, event):
        if self._cy < 0 and self._target_btn is not None and self._target_btn.height() > 0: self._cy = float(self._target_btn.geometry().center().y())
        if self._cy < 0: return
        c = current_colors(); p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); stretch = 0.0
        if self._anim.state() == QPropertyAnimation.State.Running and abs(self._end_y - self._start_y) > 1.0:
            prog = abs(self._cy - self._start_y) / abs(self._end_y - self._start_y)
            stretch = min(14.0, math.sin(min(1.0, max(0.0, prog)) * math.pi) * 14.0)
        h = 18.0 + stretch; x = (self._target_btn.geometry().left() + 3.5) if self._target_btn else 13.5
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(c["accent"])); p.drawRoundedRect(QRectF(x, self._cy - h / 2.0, 3.2, h), 1.6, 1.6)

class ModPreviewArtwork(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.setFixedSize(176, 132); self._image = QPixmap(); self._message = "未选择 MOD"

    def load_image(self, path: Path | None) -> tuple[tuple[int, int] | None, str | None]:
        self._image = QPixmap()
        if path is None or not path.is_file(): self._message = "没有预览图片"; self.update(); return None, "缺少 preview_icon.png"
        reader = QImageReader(str(path)); reader.setAutoTransform(True)
        if not reader.canRead(): self._message = "无法预览图片"; self.update(); return None, reader.errorString() or "文件无法解码"
        dims = reader.size()
        if dims.isValid(): reader.setScaledSize(dims.scaled(QSize(480, 360), Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        if image.isNull(): self._message = "无法预览图片"; self.update(); return None, reader.errorString() or "图像解码失败"
        self._image = QPixmap.fromImage(image); self._message = ""; self.update()
        return ((dims.width(), dims.height()) if dims.isValid() else (image.width(), image.height())), None

    def clear(self): self._image = QPixmap(); self._message = "未选择 MOD"; self.update()

    def paintEvent(self, event):
        c = current_colors(); app = QApplication.instance(); is_dark = (app.property("studio_theme") == "dark") if app else True; mat = app.property("studio_material") if app else "solid"
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); rect = QRectF(self.rect()).adjusted(1, 1, -1, -1); shape = QPainterPath(); shape.addRoundedRect(rect, 14, 14)
        fill = QColor(255, 255, 255, 10) if (mat == "desktop" and is_dark) else (QColor(255, 255, 255, 130) if mat == "desktop" else with_alpha(c["subtle"], 220))
        p.fillPath(shape, fill); p.save(); p.setClipPath(shape)
        if not self._image.isNull():
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform); avail = QRectF(rect).adjusted(10, 10, -10, -10)
            fit = self._image.size().scaled(QSize(round(avail.width()), round(avail.height())), Qt.AspectRatioMode.KeepAspectRatio)
            p.drawPixmap(QRectF(avail.center().x() - fit.width() / 2, avail.center().y() - fit.height() / 2, fit.width(), fit.height()), self._image, QRectF(self._image.rect()))
        else: p.setPen(QColor(c["caption"])); p.setFont(studio_font(9.0)); p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._message)
        p.restore(); p.setPen(QPen(QColor(255, 255, 255, 26) if (mat == "desktop" and is_dark) else QColor(c["card_line"]), 1)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawRoundedRect(rect, 14, 14)

class AmbientRoot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.material_mode = "desktop"; self.glass_level = 0.68; self.sidebar_width = 196; self.drag_opaque_fallback = False
        self._motion_phase = 0.0; self._glow_cache_key = None; self._glow_cache = (); self.setAutoFillBackground(False)

    def set_motion_phase(self, phase: float): self._motion_phase = float(phase); self.update()
    def _cached_glows(self, colors: dict, is_liquid: bool):
        keys = (is_liquid, colors["glow_a"], colors["glow_b"], colors["glow_c"])
        if keys == self._glow_cache_key: return self._glow_cache
        opacities = (.56, .40, .34) if is_liquid else (.24, .18, .15); cache = []
        for key, opacity in zip(("glow_a", "glow_b", "glow_c"), opacities):
            image = QPixmap(64, 64); image.fill(Qt.GlobalColor.transparent); p = QPainter(image); p.setRenderHint(QPainter.RenderHint.Antialiasing)
            g = QRadialGradient(32, 32, 31); g.setColorAt(0, with_alpha(colors[key], int(190 * opacity))); g.setColorAt(1, with_alpha(colors[key], 0))
            p.fillRect(QRectF(0, 0, 64, 64), QBrush(g)); p.end(); cache.append(image)
        self._glow_cache_key = keys; self._glow_cache = tuple(cache); return self._glow_cache

    def paintEvent(self, event):
        c = current_colors(); app = QApplication.instance(); is_dark = (app.property("studio_theme") == "dark") if app else True
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing); bounds = QRectF(self.rect())
        color_a, color_b = QColor(c["background"]), QColor(c["background2"]); strength = max(0.0, min(1.0, self.glass_level))
        if self.material_mode == "desktop" and not self.drag_opaque_fallback:
            min_alpha = 110 if is_dark else 145; max_alpha = 232 if is_dark else 240
            bg_alpha = round(max_alpha - (max_alpha - min_alpha) * strength)
            color_a.setAlpha(bg_alpha); color_b.setAlpha(max(45, bg_alpha - 14))
        else: color_a.setAlpha(255); color_b.setAlpha(255)
        gradient = QLinearGradient(0, 0, bounds.width(), bounds.height()); gradient.setColorAt(0, color_a); gradient.setColorAt(1, color_b)
        painter.fillRect(bounds, QBrush(gradient))
        sw = max(0, self.sidebar_width)
        if sw > 0:
            nav_rect = QRectF(0, 0, sw, bounds.height()); nav_grad = QLinearGradient(0, 0, 0, bounds.height()); nav_top, nav_bot = QColor(c["nav_tint"]), QColor(c["glow_b"])
            if self.material_mode == "desktop" and not self.drag_opaque_fallback:
                nav_top.setAlpha(round((52 if is_dark else 75) * (0.4 + 0.6 * strength))); nav_bot.setAlpha(round((48 if is_dark else 55) * (0.4 + 0.6 * strength)))
            elif self.material_mode == "liquid": nav_top.setAlpha(88 if is_dark else 120); nav_bot.setAlpha(60 if is_dark else 80)
            else: nav_top.setAlpha(35); nav_bot.setAlpha(15)
            nav_grad.setColorAt(0, nav_top); nav_grad.setColorAt(1, nav_bot); painter.fillRect(nav_rect, QBrush(nav_grad))
            painter.setPen(QPen(QColor(255, 255, 255, 18) if is_dark else QColor(0, 0, 0, 16), 1)); painter.drawLine(QPointF(sw, 0), QPointF(sw, bounds.height()))
        if strength <= 0.001: return
        is_liquid = (self.material_mode == "liquid"); is_desktop = (self.material_mode == "desktop")
        lights = ((.10, .12, .64), (.90, .18, .61), (.52, .94, .68)); textures = self._cached_glows(c, is_liquid)
        orb_op = strength * 0.72 if is_liquid else (strength * 0.40 if is_desktop else strength * 0.28)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setOpacity(orb_op)
        for index, ((x, y, radius), pixmap) in enumerate(zip(lights, textures)):
            r = min(bounds.width(), bounds.height()) * radius; dx = math.sin(self._motion_phase + index * 2.13) * 10.0; dy = math.cos(self._motion_phase * .71 + index * 1.76) * 7.0
            painter.drawPixmap(QRectF(bounds.width() * x - r + dx, bounds.height() * y - r + dy, r * 2, r * 2), pixmap, QRectF(pixmap.rect()))
        painter.setOpacity(1.0)

class GlassCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent); self.material_mode = "desktop"; self.glass_level = 0.68; self._selection_pulse = 0.0
        self.setObjectName("card"); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True); self.setAutoFillBackground(False)
    def get_selection_pulse(self): return self._selection_pulse
    def set_selection_pulse(self, value): self._selection_pulse = max(0.0, min(1.0, float(value))); self.update()
    selectionPulse = Property(float, get_selection_pulse, set_selection_pulse)
    def paintEvent(self, event):
        c = current_colors(); app = QApplication.instance(); is_dark = (app.property("studio_theme") == "dark") if app else True
        strength = max(0.0, min(1.0, self.glass_level)); painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.8, 0.8, -0.8, -0.8); path = QPainterPath(); path.addRoundedRect(rect, 14, 14); painter.setClipPath(path)
        if self.material_mode == "desktop":
            if is_dark:
                top_a, bot_a = round(14 + 8 * (1.0 - strength)), round(9 + 6 * (1.0 - strength))
                fill = QLinearGradient(rect.topLeft(), rect.bottomRight()); fill.setColorAt(0, QColor(255, 255, 255, top_a)); fill.setColorAt(1, QColor(255, 255, 255, bot_a)); border_col = QColor(255, 255, 255, 24)
            else:
                fill = QLinearGradient(rect.topLeft(), rect.bottomRight()); fill.setColorAt(0, QColor(255, 255, 255, round(170 - 35 * strength))); fill.setColorAt(1, QColor(255, 255, 255, round(148 - 30 * strength))); border_col = QColor(255, 255, 255, 195)
            painter.fillPath(path, QBrush(fill))
        elif self.material_mode == "liquid":
            end_a = 165 if not is_dark else 192; alpha = round(255 + (end_a - 255) * strength)
            fill = QLinearGradient(rect.topLeft(), rect.bottomRight()); fill.setColorAt(0, with_alpha(c["card"], min(255, alpha + round(22 * strength)))); fill.setColorAt(.5, with_alpha(c["card"], alpha)); fill.setColorAt(1, with_alpha(c["card"], max(120, alpha - round(16 * strength)))); painter.fillPath(path, QBrush(fill))
            if strength > 0.001:
                sheen = "#F6D8A5" if is_dark else "#FFFFFF"; gleam = QLinearGradient(rect.topLeft(), rect.topRight())
                gleam.setColorAt(0, with_alpha(sheen, 0)); gleam.setColorAt(.22, with_alpha(sheen, round(98 * strength))); gleam.setColorAt(.65, with_alpha(sheen, round(38 * strength))); gleam.setColorAt(1, with_alpha(sheen, 0))
                painter.setPen(QPen(QBrush(gleam), 1.6)); painter.drawLine(rect.topLeft() + QPointF(14, .8), rect.topRight() + QPointF(-14, .8))
            border_col = with_alpha(c["card_line"], 165)
        else: painter.fillPath(path, QColor(c["card"])); border_col = QColor(c["card_line"])
        painter.setClipping(False); painter.setPen(QPen(border_col, 1.0)); painter.setBrush(Qt.BrushStyle.NoBrush); painter.drawRoundedRect(rect, 14, 14)
        if self._selection_pulse > .001: painter.setPen(QPen(with_alpha(c["accent"], round(130 * self._selection_pulse)), 1.5)); painter.drawRoundedRect(rect.adjusted(1.2, 1.2, -1.2, -1.2), 13, 13)

class ThemeTransition(QWidget):
    def __init__(self, screenshot: QPixmap, parent=None):
        super().__init__(parent); self.image = screenshot; self._opacity = 1.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True); self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    def get_opacity(self): return self._opacity
    def set_opacity(self, alpha): self._opacity = float(alpha); self.update()
    opacityLevel = Property(float, get_opacity, set_opacity)
    def paintEvent(self, event): p = QPainter(self); p.setOpacity(max(0.0, min(1.0, self._opacity))); p.drawPixmap(self.rect(), self.image)

class SmoothButton(QFrame):
    clicked = Signal()
    def __init__(self, text: str, variant: str = "secondary", parent=None):
        super().__init__(parent); self.label_text, self.variant = text, variant
        self._hover = self._press = 0.0; self._ripple = 1.0; self._ripple_origin = QPointF(0, 0)
        self._down = self._keyboard_focus = False; self._enabled = True; self.setMinimumHeight(36); self.setMinimumWidth(92)
        self.setCursor(Qt.CursorShape.PointingHandCursor); self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.animation = QPropertyAnimation(self, b"hoverLevel", self); self.animation.setDuration(motion_duration(180)); self.animation.setEasingCurve(mac_curve())
        self._press_anim = QPropertyAnimation(self, b"pressLevel", self); self._ripple_anim = QPropertyAnimation(self, b"rippleLevel", self)
        self._ripple_anim.setDuration(motion_duration(320)); self._ripple_anim.setEasingCurve(mac_curve())

    def sizeHint(self): return QSize(max(100, len(self.label_text) * 11 + 36), 36)
    def get_hover(self): return self._hover
    def set_hover(self, v: float): self._hover = max(0.0, min(1.0, float(v))); self.update()
    hoverLevel = Property(float, get_hover, set_hover)
    def get_press(self): return self._press
    def set_press(self, v: float): self._press = max(-0.35, min(1.2, float(v))); self.update()
    pressLevel = Property(float, get_press, set_press)
    def get_ripple(self): return self._ripple
    def set_ripple(self, v: float): self._ripple = max(0.0, min(1.0, float(v))); self.update()
    rippleLevel = Property(float, get_ripple, set_ripple)

    def setEnabled(self, enabled: bool):
        self._enabled = bool(enabled)
        if not self._enabled: self._down = False; self._press_anim.stop(); self.set_press(0.0); self._ripple_anim.stop(); self.set_ripple(1.0)
        self.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor); super().setEnabled(enabled); self.update()
    def enterEvent(self, event):
        if self._enabled: self._anim(self.animation, self._hover, 1.0)
        super().enterEvent(event)
    def leaveEvent(self, event): self._anim(self.animation, self._hover, 0.0); super().leaveEvent(event)
    def _anim(self, a, start, end): a.stop(); a.setStartValue(start); a.setEndValue(end); a.start()
    def _animate_press(self, target: float):
        self._press_anim.stop()
        if target > 0.5: self._press_anim.setDuration(motion_duration(80)); self._press_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        else: self._press_anim.setDuration(motion_duration(230)); c_back = QEasingCurve(QEasingCurve.Type.OutBack); c_back.setOvershoot(1.3); self._press_anim.setEasingCurve(c_back)
        self._press_anim.setStartValue(self._press); self._press_anim.setEndValue(target); self._press_anim.start()
    def _start_ripple(self, point: QPointF): self._ripple_origin = QPointF(point); self._ripple_anim.stop(); self.set_ripple(0.0); self._ripple_anim.setStartValue(0.0); self._ripple_anim.setEndValue(1.0); self._ripple_anim.start()

    def mousePressEvent(self, event):
        if self._enabled and event.button() == Qt.MouseButton.LeftButton:
            self._down = True; self._keyboard_focus = False; self.setFocus(Qt.FocusReason.MouseFocusReason); self._animate_press(1.0); self._start_ripple(event.position()); event.accept(); return
        super().mousePressEvent(event)
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            fire = self._enabled and self._down and self.rect().contains(event.position().toPoint()); self._down = False; self._animate_press(0.0)
            if fire: self.clicked.emit()
            event.accept(); return
        super().mouseReleaseEvent(event)
    def keyPressEvent(self, event):
        if self._enabled and not event.isAutoRepeat() and event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._keyboard_focus = True; self._down = True; self._animate_press(1.0); self._start_ripple(QPointF(self.width() / 2, self.height() / 2)); event.accept(); return
        super().keyPressEvent(event)
    def keyReleaseEvent(self, event):
        if self._enabled and not event.isAutoRepeat() and self._down and event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._down = False; self._animate_press(0.0); self.clicked.emit(); event.accept(); return
        super().keyReleaseEvent(event)
    def focusInEvent(self, event):
        self._keyboard_focus = event.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason, Qt.FocusReason.ShortcutFocusReason)
        self.update(); super().focusInEvent(event)
    def focusOutEvent(self, event):
        self._keyboard_focus = False
        if self._down: self._down = False; self._animate_press(0.0)
        self.update(); super().focusOutEvent(event)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        c = current_colors(); app = QApplication.instance(); is_dark = (app.property("studio_theme") == "dark") if app else True; mat = app.property("studio_material") if app else "solid"
        if self.variant == "primary": base, hover, fg = QColor(c["accent"]), QColor(c["accent_hover"]), QColor("white")
        elif self.variant == "danger": base, hover, fg = QColor(c["danger"]), QColor(c["danger_hover"]), QColor(c["danger_text"])
        elif self.variant in ("library_check", "library_exclude", "library_clear"):
            role = self.variant.removeprefix("library_")
            base, hover, fg = QColor(c[f"library_{role}_bg"]), QColor(c[f"library_{role}_hover"]), QColor(c[f"library_{role}_ink"])
        elif mat == "desktop": base, hover, fg = QColor(255, 255, 255, 22 if is_dark else 175), QColor(255, 255, 255, 28 if is_dark else 198), QColor(c["btn_text"])
        else: base, hover, fg = QColor(c["btn"]), QColor(c["btn_hover"]), QColor(c["btn_text"])

        h_mix = 0.18 * self._hover
        bg = QColor(round(base.red() * (1 - h_mix) + hover.red() * h_mix), round(base.green() * (1 - h_mix) + hover.green() * h_mix),
                    round(base.blue() * (1 - h_mix) + hover.blue() * h_mix), round(base.alpha() * (1 - h_mix) + hover.alpha() * h_mix))
        
        # 严格保留按压时的透明通道 alpha
        if self._press > 0:
            _a = bg.alpha()
            bg = blend(bg, QColor("#06080D"), 0.28 * self._press)
            bg.setAlpha(_a)

        if not self._enabled:
            if self.variant.startswith("library_"): bg, fg = blend(bg, QColor(c["disabled"]), .46), blend(fg, QColor(c["disabled_text"]), .42)
            else: bg, fg = (QColor(255, 255, 255, 10) if (mat == "desktop" and is_dark) else QColor(c["disabled"])), QColor(c["disabled_text"])

        inset = 1.2 + 1.65 * self._press - 0.2 * self._hover * (1.0 - max(0.0, self._press))
        face = QRectF(self.rect()).adjusted(inset, inset * 0.9, -inset, -inset * 0.9)
        shape = QPainterPath(); capsule = self.variant.startswith("library_")
        shape.addRoundedRect(face, face.height() / 2 if capsule else 10, face.height() / 2 if capsule else 10)
        p.setPen(Qt.PenStyle.NoPen); p.fillPath(shape, bg)

        if capsule:
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(with_alpha(c[f"library_{self.variant.removeprefix('library_')}_line"], 200), 1)); p.drawPath(shape)
        elif self.variant == "secondary":
            rim_a = round((24 if is_dark else 20) + (12 if is_dark else 14) * self._hover)
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor(255, 255, 255, rim_a) if is_dark else QColor(0, 0, 0, rim_a), 1)); p.drawPath(shape)

        if self._enabled and self._ripple < 1.0:
            p.save(); p.setClipPath(shape); reach = math.hypot(self.width(), self.height()) * self._ripple
            ink = QColor("#0B0D14") if self.variant == "primary" else (QColor(fg) if capsule else QColor(c["ink"]))
            ink.setAlpha(int(18 * (1 - self._ripple) ** 1.8)); p.setPen(Qt.PenStyle.NoPen); p.setBrush(ink); p.drawEllipse(self._ripple_origin, reach, reach); p.restore()

        if self.hasFocus() and self._enabled and self._keyboard_focus:
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(with_alpha(c["row_active_line"], 140), 1.2)); p.drawRoundedRect(face.adjusted(0.8, 0.8, -0.8, -0.8), 9, 9)

        p.setPen(fg); p.setFont(studio_font(9.0 if capsule else 9.5, QFont.Weight.DemiBold)); p.drawText(self.rect().translated(0, round(max(0.0, self._press) * 0.8)), Qt.AlignmentFlag.AlignCenter, self.label_text)

class SegmentedControl(QWidget):
    valueChanged = Signal(str)
    def __init__(self, options: tuple[tuple[str, str], ...], current: str, width_px: int | None = 234, parent=None, *, height_px: int = 36):
        super().__init__(parent); self._keys = tuple(k for k, _ in options); self._captions = tuple(lbl for _, lbl in options)
        self._value = current if current in self._keys else self._keys[0]; self._position = float(self._keys.index(self._value)); self._hovered = -1; self._press = 0.0
        if width_px is not None:
            self.setFixedSize(width_px, height_px)
        else:
            self.setMinimumWidth(180)
            self.setFixedHeight(height_px); self.setFocusPolicy(Qt.FocusPolicy.StrongFocus); self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._slide = QPropertyAnimation(self, b"selectionPosition", self); self._slide.setDuration(motion_duration(320))
        curve = QEasingCurve(QEasingCurve.Type.OutBack); curve.setOvershoot(0.95); self._slide.setEasingCurve(curve)
        self._press_anim = QPropertyAnimation(self, b"pressScale", self); self._press_anim.setDuration(motion_duration(180))

    def get_position(self): return self._position
    def set_position(self, value): self._position = float(value); self.update()
    selectionPosition = Property(float, get_position, set_position)
    def get_press_scale(self): return self._press
    def set_press_scale(self, value): self._press = max(-0.2, min(1.0, float(value))); self.update()
    pressScale = Property(float, get_press_scale, set_press_scale)

    def set_value(self, val: str, *, emit: bool = True, animated: bool = True):
        if val not in self._keys: return
        changed = val != self._value; self._value = val; end = float(self._keys.index(val)); self._slide.stop()
        if animated and self.isVisible(): self._slide.setStartValue(self._position); self._slide.setEndValue(end); self._slide.start()
        else: self.set_position(end)
        if changed and emit: self.valueChanged.emit(val)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_anim.stop(); self._press_anim.setEasingCurve(QEasingCurve.Type.OutQuad); self._press_anim.setStartValue(self._press); self._press_anim.setEndValue(1.0); self._press_anim.start()
        super().mousePressEvent(event)
    def mouseReleaseEvent(self, event):
        self._press_anim.stop(); c_back = QEasingCurve(QEasingCurve.Type.OutBack); c_back.setOvershoot(1.2)
        self._press_anim.setEasingCurve(c_back); self._press_anim.setStartValue(self._press); self._press_anim.setEndValue(0.0); self._press_anim.start()
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            n = len(self._keys); self.set_value(self._keys[min(n - 1, max(0, int(event.position().x() * n / self.width())))]); self.setFocus(); event.accept(); return
        super().mouseReleaseEvent(event)
    def mouseMoveEvent(self, event):
        n = len(self._keys); idx = min(n - 1, max(0, int(event.position().x() * n / self.width())))
        if idx != self._hovered: self._hovered = idx; self.update()
        super().mouseMoveEvent(event)
    def leaveEvent(self, event): self._hovered = -1; self.update(); super().leaveEvent(event)
    def keyPressEvent(self, event):
        n = len(self._keys)
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Home, Qt.Key.Key_End):
            idx = self._keys.index(self._value)
            idx = 0 if event.key() == Qt.Key.Key_Home else (n - 1 if event.key() == Qt.Key.Key_End else (max(0, idx - 1) if event.key() == Qt.Key.Key_Left else min(n - 1, idx + 1)))
            self.set_value(self._keys[idx]); event.accept(); return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        c = current_colors(); app = QApplication.instance(); is_dark = (app.property("studio_theme") == "dark") if app else True; mat = app.property("studio_material") if app else "solid"
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        track_bg = QColor(255, 255, 255, 16) if (mat == "desktop" and is_dark) else (QColor(0, 0, 0, 14) if mat == "desktop" else QColor(c["btn"]))
        p.setPen(QPen(QColor(255, 255, 255, 26) if (mat == "desktop" and is_dark) else with_alpha(c["card_line"], 120), 1))
        p.setBrush(track_bg); p.drawRoundedRect(rect, 11, 11)
        n = len(self._keys); w = (self.width() - 6) / n; pad = 1.0 * self._press
        ind_rect = QRectF(3 + self._position * w + pad, 3 + pad * 0.8, w - 2 * pad, self.height() - 6 - 1.6 * pad)
        if mat == "desktop" and is_dark:
            ind_bg, ind_line = QColor(255, 255, 255, 36), QColor(255, 255, 255, 52)
        else:
            ind_bg, ind_line = QColor(c["card"]), with_alpha(c["row_active_line"], 130)
        p.setPen(QPen(ind_line, .95)); p.setBrush(ind_bg); p.drawRoundedRect(ind_rect, 9, 9)
        p.setFont(studio_font(9.2, QFont.Weight.DemiBold)); active = self._keys.index(self._value)
        for i, caption in enumerate(self._captions):
            seg = QRectF(3 + i * w, 3, w, self.height() - 6)
            if self._hovered == i and i != active: p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(255, 255, 255, 16) if is_dark else with_alpha(c["accent"], 18)); p.drawRoundedRect(seg.adjusted(3, 3, -3, -3), 7, 7)
            p.setPen(QColor(c["ink"] if i == active else c["muted"])); p.drawText(seg, Qt.AlignmentFlag.AlignCenter, caption)

class ColorSwatch(QWidget):
    picked = Signal(str)

    def __init__(self, hex_color: str, tooltip: str = "", parent=None):
        super().__init__(parent)
        self.hex_color = hex_color.upper()
        self._active = False
        self._hover = self._press = 0.0
        self.setFixedSize(26, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip: self.setToolTip(f"{tooltip} ({self.hex_color})")
        self._p_anim = QPropertyAnimation(self, b"pressScale", self)

    def get_press(self): return self._press
    def set_press(self, v: float): self._press = max(-0.2, min(1.0, float(v))); self.update()
    pressScale = Property(float, get_press, set_press)

    def set_active(self, active: bool):
        if self._active != bool(active): self._active = bool(active); self.update()
    def enterEvent(self, event): self._hover = 1.0; self.update(); super().enterEvent(event)
    def leaveEvent(self, event): self._hover = 0.0; self.update(); super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._p_anim.stop(); self._p_anim.setDuration(motion_duration(80))
            self._p_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            self._p_anim.setStartValue(self._press); self._p_anim.setEndValue(1.0); self._p_anim.start()
            event.accept(); return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._p_anim.stop(); self._p_anim.setDuration(motion_duration(200))
        cb = QEasingCurve(QEasingCurve.Type.OutBack); cb.setOvershoot(1.4)
        self._p_anim.setEasingCurve(cb); self._p_anim.setStartValue(self._press); self._p_anim.setEndValue(0.0); self._p_anim.start()
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.picked.emit(self.hex_color); event.accept(); return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        c = current_colors(); p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        if self._active:
            p.setPen(QPen(QColor(c["ink"]), 1.8)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), 11.2, 11.2)
        elif self._hover > 0.5:
            p.setPen(QPen(with_alpha(c["ink"], 110), 1.2)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), 11.0, 11.0)
        r = 8.4 - 1.3 * self._press
        p.setPen(QPen(QColor(255, 255, 255, 80), 0.9))
        p.setBrush(QColor(self.hex_color))
        p.drawEllipse(QPointF(cx, cy), r, r)

class StatusPill(QWidget):
    def __init__(self, initial="READY", parent=None):
        super().__init__(parent); self._state = initial; self._pulse = 0.0; self.setFixedSize(112, 30)
        self._pulse_anim = QPropertyAnimation(self, b"pulseLevel", self); self._pulse_anim.setDuration(motion_duration(620)); self._pulse_anim.setEasingCurve(mac_curve())
    def setText(self, state: str):
        state = str(state)
        if state != self._state: self._state = state; self._pulse_anim.stop(); self.set_pulse(1.0); self._pulse_anim.setStartValue(1.0); self._pulse_anim.setEndValue(0.0); self._pulse_anim.start()
        self.update()
    def get_pulse(self): return self._pulse
    def set_pulse(self, value): self._pulse = max(0.0, min(1.0, float(value))); self.update()
    pulseLevel = Property(float, get_pulse, set_pulse)
    def paintEvent(self, event):
        c = current_colors(); p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        sig = QColor("#3B9A77") if self._state == "COMPLETE" else (QColor(c["danger_text"]) if self._state == "CHECK LOG" else (QColor(c["accent"]) if self._state in ("UPLOADING", "PREPARING", "STOPPING", "CLEANING") else QColor(c["muted"])))
        p.setPen(QPen(with_alpha(sig.name(), 80 + round(self._pulse * 120)), 1.0 + self._pulse)); p.setBrush(QColor(c["accent_soft"])); p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 11, 11)
        p.setFont(studio_font(8.8, QFont.Weight.DemiBold)); p.setPen(sig); p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._state)

class StudioDialog(QDialog):
    def __init__(self, parent, heading: str, detail: str, *, confirm: bool = False, severity: str = "info", confirm_text: str = "继续更新", cancel_text: str = "取消"):
        super().__init__(parent); self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True); self.setMinimumWidth(450); self.setMaximumWidth(550); c = current_colors(); app = QApplication.instance(); mat = app.property("studio_material") if app else "solid"
        panel_bg = with_alpha(c["card"], 240 if mat != "solid" else 255).name(QColor.NameFormat.HexArgb)
        outer = QVBoxLayout(self); outer.setContentsMargins(22, 23, 22, 29); panel = QFrame(self); panel.setObjectName("studioDialogPanel")
        panel.setStyleSheet(f"QFrame#studioDialogPanel {{ background-color: {panel_bg}; border: 1px solid {c['card_line']}; border-radius: 18px; }} QLabel#studioDialogEyebrow {{ border: none; color: {c['caption']}; font-size: 9pt; font-weight: 700; }} QLabel#studioDialogTitle {{ border: none; color: {c['ink']}; font-size: 13pt; font-weight: 700; }} QLabel#studioDialogBody {{ border: none; color: {c['label']}; font-size: 10pt; }} QLabel#studioDialogIcon {{ border: none; color: {c['accent'] if severity != 'error' else c['danger_text']}; background-color: {c['accent_soft'] if severity != 'error' else c['danger']}; border-radius: 16px; font-size: 13pt; font-weight: 700; }}")
        self._panel = panel; outer.addWidget(panel); v = QVBoxLayout(panel); v.setContentsMargins(25, 23, 25, 23); v.setSpacing(14)
        tag = QLabel("DD WORKSHOP STUDIO  /  PRIVATE ARCHIVE"); tag.setObjectName("studioDialogEyebrow"); v.addWidget(tag)
        row = QHBoxLayout(); row.setSpacing(12); icon = QLabel("!" if confirm or severity == "error" else "i"); icon.setObjectName("studioDialogIcon"); icon.setFixedSize(34, 34); icon.setAlignment(Qt.AlignmentFlag.AlignCenter); row.addWidget(icon)
        title = QLabel(heading); title.setObjectName("studioDialogTitle"); title.setWordWrap(True); row.addWidget(title, 1); v.addLayout(row)
        desc = QLabel(detail); desc.setObjectName("studioDialogBody"); desc.setWordWrap(True); desc.setTextFormat(Qt.TextFormat.PlainText); desc.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); desc.setMinimumHeight(45); v.addWidget(desc); v.addSpacing(5)
        btns = QHBoxLayout(); btns.setSpacing(10); btns.addStretch(1)
        if confirm:
            d = SmoothButton(cancel_text); d.setFixedWidth(98); d.clicked.connect(self.reject); btns.addWidget(d)
            a = SmoothButton(confirm_text, "primary"); a.setFixedWidth(112); a.clicked.connect(self.accept); btns.addWidget(a); d.setFocus()
        else: a = SmoothButton("知道了", "primary"); a.setFixedWidth(112); a.clicked.connect(self.accept); btns.addWidget(a); a.setFocus()
        v.addLayout(btns); self._entrance = QPropertyAnimation(self, b"windowOpacity", self); self._entrance.setDuration(motion_duration(260)); self._entrance.setEasingCurve(mac_curve()); self._entrance.setStartValue(0.0); self._entrance.setEndValue(1.0); self.adjustSize(); self.resize(520, self.height()); QTimer.singleShot(0, self._start_entrance)
    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); g = QRectF(self._panel.geometry())
        for i in range(11, 0, -1): p.setPen(QPen(QColor(0, 0, 0, round(2.6 if i > 7 else 4.2)), 1.5)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawRoundedRect(g.adjusted(-i * 1.5, -i * 1.1, i * 1.5, i * 1.9), 18 + i, 18 + i)
    def _start_entrance(self):
        if self.parentWidget() is not None: c = self.parentWidget().mapToGlobal(self.parentWidget().rect().center()); self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)
        self.setWindowOpacity(0.0); self._entrance.start()
    @classmethod
    def information(cls, parent, heading: str, detail: str, *, severity: str = "info"): cls(parent, heading, detail, severity=severity).exec()
    @classmethod
    def ask(cls, parent, heading: str, detail: str, *, confirm_text: str = "继续更新", cancel_text: str = "取消") -> bool: return cls(parent, heading, detail, confirm=True, confirm_text=confirm_text, cancel_text=cancel_text).exec() == QDialog.DialogCode.Accepted

class SmoothSlider(QSlider):
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setMinimumHeight(24)

    def paintEvent(self, event):
        c = current_colors()
        app = QApplication.instance()
        is_dark = (app.property("studio_theme") == "dark") if app else True
        mat = app.property("studio_material") if app else "solid"
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        span = max(1, self.maximum() - self.minimum())
        ratio = (self.value() - self.minimum()) / span
        pad = 9.0
        track_w = max(1.0, self.width() - pad * 2)
        cy = self.height() / 2.0
        groove_col = (
            QColor(255, 255, 255, 34) if (mat == "desktop" and is_dark)
            else (QColor(15, 23, 42, 34) if mat == "desktop" else QColor(c["card_line"]))
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(groove_col)
        p.drawRoundedRect(QRectF(pad, cy - 2.5, track_w, 5.0), 2.5, 2.5)
        fill_w = track_w * ratio
        if fill_w > 0.5:
            p.setBrush(QColor(c["accent"]))
            p.drawRoundedRect(QRectF(pad, cy - 2.5, fill_w, 5.0), 2.5, 2.5)
        p.setPen(QPen(QColor(c["accent"]), 2.2))
        p.setBrush(QColor(c["card"]))
        p.drawEllipse(QPointF(pad + fill_w, cy), 7.2, 7.2)


class AccentBadge(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(26)
        self.setMinimumWidth(78)

    def paintEvent(self, event):
        c = current_colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c["accent_soft"]))
        p.drawRoundedRect(rect, 9.0, 9.0)
        p.setPen(QColor(c["ink"]))
        p.setFont(studio_font(8.8, QFont.Weight.DemiBold))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())



class StudioColorDialog(QDialog):
    colorChanged = Signal(QColor)
    _ZH_MAP = {
        "basic colors": "基础色板",
        "custom colors": "自定义色板",
        "pick screen color": "屏幕取色",
        "add to custom colors": "添加到自定义色板",
        "hue": "色相(H):",
        "sat": "饱和(S):",
        "val": "明度(V):",
        "red": "红(R):",
        "green": "绿(G):",
        "blue": "蓝(B):",
        "html": "色值:",
        "alpha channel": "透明度:",
    }

    def __init__(self, parent, initial_color: str | QColor):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self._drag_pos: QPointF | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 26)
        self._panel = QFrame(self)
        self._panel.setObjectName("colorDialogPanel")
        outer.addWidget(self._panel)

        v = QVBoxLayout(self._panel)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)

        tag = QLabel("DD WORKSHOP STUDIO  /  CUSTOM COLOR")
        tag.setObjectName("colorDialogEyebrow")
        v.addWidget(tag)

        title = QLabel("自由调色 · 拖动色轮实时预览")
        title.setObjectName("colorDialogTitle")
        v.addWidget(title)

        self._picker = QColorDialog(QColor(initial_color), self._panel)
        self._picker.setWindowFlags(Qt.WindowType.Widget)
        self._picker.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        self._picker.setOption(QColorDialog.ColorDialogOption.NoButtons, True)
        self._translate_picker()
        self._picker.currentColorChanged.connect(self._on_color_changed)
        v.addWidget(self._picker)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        btns.addStretch(1)
        self._cancel_btn = SmoothButton("取消")
        self._cancel_btn.setFixedWidth(96)
        self._cancel_btn.clicked.connect(self.reject)
        self._ok_btn = SmoothButton("确定", "primary")
        self._ok_btn.setFixedWidth(108)
        self._ok_btn.clicked.connect(self.accept)
        btns.addWidget(self._cancel_btn)
        btns.addWidget(self._ok_btn)
        v.addLayout(btns)

        self.refresh_theme()
        self.adjustSize()
        self._entrance = QPropertyAnimation(self, b"windowOpacity", self)
        self._entrance.setDuration(motion_duration(220))
        self._entrance.setEasingCurve(mac_curve())
        self._entrance.setStartValue(0.0)
        self._entrance.setEndValue(1.0)
        QTimer.singleShot(0, self._start_entrance)

    def _translate_picker(self):
        for w in self._picker.findChildren(QLabel) + self._picker.findChildren(QPushButton):
            raw = w.text()
            key = raw.replace("&", "").strip().rstrip(":").casefold()
            if key in self._ZH_MAP:
                w.setText(self._ZH_MAP[key])

    def refresh_theme(self):
        c = current_colors()
        app = QApplication.instance()
        mat = app.property("studio_material") if app else "solid"
        col_card = QColor(c["card"])
        panel_bg = f"rgba({col_card.red()}, {col_card.green()}, {col_card.blue()}, {250 if mat != 'solid' else 255})"
        self._panel.setStyleSheet(
            f"QFrame#colorDialogPanel {{ background-color: {panel_bg}; border: 1px solid {c['card_line']}; border-radius: 18px; }}"
            f"QFrame#colorDialogPanel QLabel {{ color: {c['label']}; font-size: 9.2pt; background: transparent; }}"
            f"QFrame#colorDialogPanel QLabel#colorDialogEyebrow {{ color: {c['caption']}; font-size: 9pt; font-weight: 700; }}"
            f"QFrame#colorDialogPanel QLabel#colorDialogTitle {{ color: {c['ink']}; font-size: 13pt; font-weight: 700; }}"
            f"QFrame#colorDialogPanel QLineEdit, QFrame#colorDialogPanel QSpinBox {{ color: {c['ink']}; background: {c['input']}; border: 1px solid {c['card_line']}; border-radius: 8px; padding: 4px 8px; selection-background-color: {c['highlight']}; }}"
            f"QFrame#colorDialogPanel QLineEdit:focus, QFrame#colorDialogPanel QSpinBox:focus {{ border: 1px solid {c['accent']}; }}"
            f"QFrame#colorDialogPanel QPushButton {{ color: {c['btn_text']}; background: {c['btn']}; border: 1px solid {c['card_line']}; border-radius: 9px; padding: 6px 12px; font-size: 9.2pt; font-weight: 600; }}"
            f"QFrame#colorDialogPanel QPushButton:hover {{ background: {c['btn_hover']}; border-color: {c['row_active_line']}; }}"
        )
        self._cancel_btn.update()
        self._ok_btn.update()

    def _on_color_changed(self, col: QColor):
        self.colorChanged.emit(col)
        QTimer.singleShot(0, self.refresh_theme)

    def selectedColor(self) -> QColor:
        return self._picker.currentColor()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 90:
            self._drag_pos = event.globalPosition() - QPointF(self.pos())
            event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move((event.globalPosition() - self._drag_pos).toPoint())
            event.accept(); return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QRectF(self._panel.geometry())
        for i in range(11, 0, -1):
            p.setPen(QPen(QColor(0, 0, 0, round(2.6 if i > 7 else 4.2)), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(g.adjusted(-i * 1.5, -i * 1.1, i * 1.5, i * 1.9), 18 + i, 18 + i)

    def _start_entrance(self):
        if self.parentWidget() is not None:
            c = self.parentWidget().mapToGlobal(self.parentWidget().rect().center())
            self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)
        self.setWindowOpacity(0.0)
        self._entrance.start()



class StudioMenu(QMenu):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setContentsMargins(8, 8, 8, 8)
        self.setFont(studio_font(9.4))
        c = current_colors()
        acc = QColor(c["accent"])
        bd = QColor(c["row_active_line"])
        hover_bg = f"rgba({acc.red()}, {acc.green()}, {acc.blue()}, 54)"
        hover_bd = f"rgba({bd.red()}, {bd.green()}, {bd.blue()}, 170)"
        self.setStyleSheet(
            f"QMenu {{ background: transparent; border: none; padding: 4px; color: {c['ink']}; }}"
            f"QMenu::item {{ background: transparent; padding: 7px 16px; border-radius: 8px; margin: 1px 0; border: 1px solid transparent; }}"
            f"QMenu::item:selected {{ background: {hover_bg}; border: 1px solid {hover_bd}; color: {c['ink']}; }}"
            f"QMenu::item:disabled {{ color: {c['disabled_text']}; }}"
            f"QMenu::separator {{ height: 1px; background: {c['card_line']}; margin: 5px 10px; }}"
        )

    def paintEvent(self, event):
        c = current_colors()
        app = QApplication.instance()
        is_dark = (app.property("studio_theme") == "dark") if app else True
        mat = app.property("studio_material") if app else "solid"
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(6.0, 6.0, -6.0, -6.0)
        for i in range(5, 0, -1):
            p.setPen(QPen(QColor(0, 0, 0, round(4.2 * (6 - i))), 1.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(-i * 0.9, -i * 0.6, i * 0.9, i * 1.1), 12 + i * 0.6, 12 + i * 0.6)
        path = QPainterPath()
        path.addRoundedRect(rect, 12.0, 12.0)
        alpha = 248 if mat != "solid" else 255
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0, with_alpha(c["card"], alpha))
        grad.setColorAt(1, with_alpha(c["background2"], alpha))
        p.fillPath(path, QBrush(grad))
        if mat != "solid":
            sheen = "#F6D8A5" if is_dark else "#FFFFFF"
            gleam = QLinearGradient(rect.topLeft(), rect.topRight())
            gleam.setColorAt(0, with_alpha(sheen, 0))
            gleam.setColorAt(0.25, with_alpha(sheen, 95 if is_dark else 160))
            gleam.setColorAt(0.75, with_alpha(sheen, 35 if is_dark else 90))
            gleam.setColorAt(1, with_alpha(sheen, 0))
            p.setPen(QPen(QBrush(gleam), 1.4))
            p.drawLine(rect.topLeft() + QPointF(12, 0.8), rect.topRight() + QPointF(-12, 0.8))
        p.setPen(QPen(QColor(c["card_line"]), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 12.0, 12.0)
        p.end()
        super().paintEvent(event)
