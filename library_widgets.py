"""MOD library tree rows, headers and background archive/cleanup workers."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re

from PySide6.QtCore import Property, QEvent, QPoint, QPropertyAnimation, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QDialog, QFrame, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QSizePolicy, QVBoxLayout,
)
from studio_widgets import SegmentedControl, SmoothButton

from archiver_core import (
    ModEntry, WORKSHOP_URL, _read_json, cleanup_successful_workspace,
    description_for, prepare_project, upload_title_for, project_dir, read_own_id, upload_project,
)
from studio_theme import current_colors, mac_curve, motion_duration, with_alpha


class ElidedNameLabel(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setWordWrap(False)
        self.setToolTip(text)
        self.setAccessibleName(text)
        self._update_elision()

    def set_full_text(self, text: str):
        self._full_text = text
        self.setToolTip(text)
        self.setAccessibleName(text)
        self._update_elision()

    def _update_elision(self):
        available = max(0, self.contentsRect().width())
        rendered = self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideRight, available)
        if self.text() != rendered:
            super().setText(rendered)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elision()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._update_elision()


class CollectionCheckBox(QCheckBox):
    def nextCheckState(self):
        self.setCheckState(
            Qt.CheckState.Unchecked if self.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
        )


class ModCollectionHeader(QFrame):
    expanded_changed = Signal(str, bool)
    highlighted = Signal(str, int)
    checked_changed = Signal(str, bool)

    def __init__(self, group_id: str, title: str, total: int, expanded: bool, parent=None):
        super().__init__(parent)
        self.group_id = group_id
        self._expanded = bool(expanded)
        self._hover = self._pressed = self._highlighted = False
        self.setObjectName("modCollection")
        self.setFixedHeight(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        tip_head = f"按工坊标签分组：{title}" if group_id.startswith("tag:") else group_id
        self.setToolTip(f"{tip_head}\n单击展开/收起并高亮整组；右侧方框可直接勾选/排除整组 MOD。")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(11, 6, 10, 6)
        layout.setSpacing(9)
        self.arrow = QLabel(); self.arrow.setObjectName("collectionArrow"); self.arrow.setFixedWidth(15)
        self.arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name = ElidedNameLabel(title); self.name.setObjectName("collectionName")
        self.summary = QLabel(); self.summary.setObjectName("collectionSummary")
        self.summary.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.check = CollectionCheckBox(); self.check.setTristate(True)
        self.check.clicked.connect(lambda v: self.checked_changed.emit(self.group_id, bool(v)))
        for lbl in (self.arrow, self.name, self.summary):
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.arrow); layout.addWidget(self.name, 1)
        layout.addWidget(self.check); layout.addWidget(self.summary)
        self.set_expanded(expanded); self.update_summary(total, 0)

    def set_expanded(self, expanded: bool):
        self._expanded = bool(expanded)
        self.arrow.setText("▾" if self._expanded else "▸")
        self.update()

    def update_summary(self, total: int, checked: int):
        self.summary.setText(f"{checked}/{total}")
        state = Qt.CheckState.Unchecked if (not total or checked == 0) else (
            Qt.CheckState.Checked if checked == total else Qt.CheckState.PartiallyChecked
        )
        self.check.blockSignals(True); self.check.setCheckState(state); self.check.blockSignals(False)

    def set_highlighted(self, highlighted: bool):
        if self._highlighted != bool(highlighted):
            self._highlighted = bool(highlighted); self.update()

    def enterEvent(self, event): self._hover = True; self.update(); super().enterEvent(event)
    def leaveEvent(self, event): self._hover = False; self.update(); super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True; self.setFocus(Qt.FocusReason.MouseFocusReason); event.accept(); return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            was = self._pressed; self._pressed = False
            if was and self.rect().contains(event.position().toPoint()):
                self.highlighted.emit(self.group_id, int(event.modifiers().value))
                self.expanded_changed.emit(self.group_id, not self._expanded)
            event.accept(); return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.highlighted.emit(self.group_id, int(event.modifiers().value))
            self.expanded_changed.emit(self.group_id, not self._expanded); event.accept(); return
        if event.key() == Qt.Key.Key_Left:
            self.expanded_changed.emit(self.group_id, False); event.accept(); return
        if event.key() == Qt.Key.Key_Right:
            self.expanded_changed.emit(self.group_id, True); event.accept(); return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = current_colors()
        app = QApplication.instance()
        is_dark = (app.property("studio_theme") == "dark") if app else True
        mat = app.property("studio_material") if app else "solid"
        rect = QRectF(self.rect()).adjusted(0.8, 0.8, -0.8, -0.8)
        hl = self._hover or self._highlighted
        if mat == "desktop":
            bg = with_alpha(c["accent"], 40 if is_dark else 28) if hl else (QColor(255, 255, 255, 13) if is_dark else QColor(255, 255, 255, 165))
            line = with_alpha(c["row_active_line"], 180) if hl else (QColor(255, 255, 255, 22) if is_dark else QColor(0, 0, 0, 20))
        else:
            bg = QColor(c["row_active"] if hl else c["subtle"])
            line = QColor(c["row_active_line"] if hl else c["card_line"])
        p.setBrush(bg); p.setPen(QPen(line, 1)); p.drawRoundedRect(rect, 11, 11)


class ModRow(QFrame):
    selected_row = Signal(str, int)
    selected_checked = Signal(str, bool)
    context_requested = Signal(str, QPoint)

    def __init__(self, item: ModEntry, parent=None):
        super().__init__(parent)
        self.item = item
        self.key = str(item.source)
        self._hover = self._selection = self._tap = 0.0
        self._active = False
        self.setObjectName("modRow")
        self.setMinimumHeight(68); self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(str(item.source))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self); layout.setContentsMargins(12, 8, 12, 8); layout.setSpacing(10)
        self.box = QCheckBox(); self.box.setChecked(item.selected)
        self.box.setCursor(Qt.CursorShape.PointingHandCursor)
        self.box.stateChanged.connect(lambda st: self.selected_checked.emit(self.key, st == Qt.CheckState.Checked.value))
        layout.addWidget(self.box)
        content = QVBoxLayout(); content.setSpacing(3)
        self.title = ElidedNameLabel(item.source.name); self.title.setObjectName("rowTitle")
        self.status = ElidedNameLabel(); self.status.setObjectName("rowSub"); self.status.setMinimumWidth(0)
        self.update_content(item)
        content.addWidget(self.title); content.addWidget(self.status); layout.addLayout(content, 1)

        self._hover_anim = QPropertyAnimation(self, b"hoverLevel", self)
        self._hover_anim.setDuration(motion_duration(210)); self._hover_anim.setEasingCurve(mac_curve())
        self._select_anim = QPropertyAnimation(self, b"selectionLevel", self)
        self._select_anim.setDuration(motion_duration(270)); self._select_anim.setEasingCurve(mac_curve())
        self._tap_anim = QPropertyAnimation(self, b"tapLevel", self)
        self._tap_anim.setDuration(motion_duration(350)); self._tap_anim.setEasingCurve(mac_curve())

    def get_hover(self): return self._hover
    def set_hover(self, v): self._hover = max(0.0, min(1.0, float(v))); self.update()
    hoverLevel = Property(float, get_hover, set_hover)

    def get_selection(self): return self._selection
    def set_selection(self, v): self._selection = max(0.0, min(1.0, float(v))); self.update()
    selectionLevel = Property(float, get_selection, set_selection)

    def get_tap(self): return self._tap
    def set_tap(self, v): self._tap = max(0.0, min(1.0, float(v))); self.update()
    tapLevel = Property(float, get_tap, set_tap)

    def _animate_to(self, a, cur, target):
        a.stop(); a.setStartValue(cur); a.setEndValue(target); a.start()

    def flash(self):
        self._tap_anim.stop(); self.set_tap(1.0)
        self._tap_anim.setStartValue(1.0); self._tap_anim.setEndValue(0.0); self._tap_anim.start()

    def update_content(self, item: ModEntry):
        old = getattr(self, "item", None)
        prev = old.status if old is not None else None
        self.item = item
        self.title.set_full_text(re.sub(r"[\r\n\t]+", " ", item.title).strip() or item.source.name)
        self.box.blockSignals(True); self.box.setChecked(item.selected); self.box.blockSignals(False)
        if item.status == "SUCCESS": desc = "已上传"
        elif item.status == "UNCONFIRMED": desc = "提交未确认"
        elif item.own_id: desc = "已有本地工坊 ID"
        elif item.original_ids: desc = f"已识别 {len(item.original_ids)} 个来源 ID"
        else: desc = "未检测到来源 ID"
        tag_txt = ", ".join(item.tags) if item.tags else "未设标签"
        self.status.set_full_text(f"{desc} · {tag_txt}")
        if prev is not None and item.status != prev and hasattr(self, "_tap_anim"):
            self.flash()

    def set_active(self, active: bool):
        if self._active != bool(active):
            self._active = bool(active)
            self._animate_to(self._select_anim, self._selection, 1.0 if active else 0.0)

    def enterEvent(self, event): self._animate_to(self._hover_anim, self._hover, 1.0); super().enterEvent(event)
    def leaveEvent(self, event): self._animate_to(self._hover_anim, self._hover, 0.0); super().leaveEvent(event)

    def contextMenuEvent(self, event):
        self.context_requested.emit(self.key, event.globalPos())
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason); self.flash()
            self.selected_row.emit(self.key, int(event.modifiers().value)); event.accept(); return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.flash(); self.selected_row.emit(self.key, int(event.modifiers().value)); event.accept(); return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = current_colors()
        rect = QRectF(self.rect()).adjusted(0.8, 0.8, -0.8, -0.8)
        mask = QPainterPath(); mask.addRoundedRect(rect, 11, 11)
        alpha = round(16 * self._hover + 30 * self._selection + 16 * self._tap)
        if alpha: p.fillPath(mask, with_alpha(c["accent"], alpha))
        b_alpha = round(220 * self._selection + 60 * self._hover)
        if b_alpha:
            p.setPen(QPen(with_alpha(c["row_active_line"], b_alpha), 1.35))
            p.setBrush(Qt.BrushStyle.NoBrush); p.drawRoundedRect(rect, 11, 11)


class PipelineWorker(QThread):
    line = Signal(str)
    changed = Signal(str, str, str)
    progress = Signal(int)
    completed = Signal(int, int, bool)

    def __init__(self, items: list[ModEntry], workspace: Path, uploader: Path, upload: bool, allow_update: bool, strip_numbers: bool = False, strip_v2: bool = False):
        super().__init__()
        self.items = [replace(item, original_ids=dict(item.original_ids), tags=list(item.tags)) for item in items]
        self.workspace, self.uploader, self.upload, self.allow_update, self.strip_numbers, self.strip_v2 = workspace, uploader, upload, allow_update, bool(strip_numbers), bool(strip_v2)
        self.stop_requested = False

    def run(self):
        done = failures = 0
        total = len(self.items)
        for index, item in enumerate(self.items):
            if self.stop_requested:
                self.line.emit("已按请求停止后续任务。"); break
            self.line.emit(f"\n[{index + 1}/{total}] {item.source.name}")
            key = str(item.source)
            try:
                if not upload_title_for(item, strip_numbers=self.strip_numbers, strip_v2=self.strip_v2): raise RuntimeError("上传标题不能为空")
                if len(description_for(item, strip_numbers=self.strip_numbers, strip_v2=self.strip_v2)) > 12000: raise RuntimeError("描述文字过长（超过 12000 字符）")
                folder = project_dir(self.workspace, item.source)
                state = _read_json(folder / "status.json")
                existing_id = read_own_id(folder / "upload.xml")
                if self.upload and not self.allow_update:
                    if state.get("status") == "SUCCESS" and existing_id:
                        self.line.emit("  已上传成功，跳过；要重新提交请勾选『允许更新已有项目』。")
                        self.changed.emit(key, "SUCCESS", existing_id); done += 1
                        self.progress.emit(round((index + 1) / total * 100)); continue
                    if existing_id or state.get("status") == "UNCONFIRMED":
                        raise RuntimeError(f"此项目已有 ID（{existing_id or '未知'}）或曾提交失败，已停止。")
                path = prepare_project(item, self.workspace, self.line.emit, strip_numbers=self.strip_numbers, strip_v2=self.strip_v2)
                self.line.emit(f"  已生成上传 XML：{path}")
                if not self.upload:
                    self.changed.emit(key, "READY", read_own_id(path))
                else:
                    success, own_id = upload_project(item, self.workspace, self.uploader, self.line.emit)
                    if not success:
                        self.changed.emit(key, "UNCONFIRMED", own_id)
                        raise RuntimeError(f"提交未确认成功；当前工坊 ID：{own_id or '无'}。请检查日志。")
                    self.changed.emit(key, "SUCCESS", own_id)
                    self.line.emit("  ✓ 上传已确认完成：" + WORKSHOP_URL.format(own_id))
                done += 1
            except Exception as exc:
                failures += 1
                self.line.emit(f"  ✕ {type(exc).__name__}: {exc}")
                self.line.emit("已停止后续任务，请先检查并修复此 MOD。"); break
            finally:
                self.progress.emit(round((index + 1) / total * 100))
        self.completed.emit(done, failures, self.stop_requested)


class CacheCleanupWorker(QThread):
    line = Signal(str)
    completed = Signal(int, int, int, int)

    def __init__(self, workspace: Path):
        super().__init__()
        self.workspace = workspace

    def run(self):
        try:
            report = cleanup_successful_workspace(self.workspace, self.line.emit)
            self.completed.emit(report.projects_cleaned, report.bytes_freed, report.projects_skipped, len(report.errors))
            for err in report.errors[:12]:
                self.line.emit(f"  ⚠ 清理失败：{err}")
        except Exception as exc:
            self.line.emit(f"  ✕ 清理缓存异常：{type(exc).__name__}: {exc}")
            self.completed.emit(0, 0, 0, 1)



def compute_reordered_numbers(orig_nums: list[int | None], mode: str) -> list[int]:
    """Calculate new collection numbers for the current row sequence."""
    n = len(orig_nums)
    if mode == "compact":
        return list(range(1, n + 1))

    numbered = [(idx, num) for idx, num in enumerate(orig_nums) if num is not None]
    anchor_indices: set[int] = set()
    if numbered:
        m = len(numbered)
        dp = [1] * m
        prev_idx = [-1] * m
        best_i = 0
        for i in range(m):
            for j in range(i):
                if numbered[j][1] < numbered[i][1] and dp[j] + 1 > dp[i]:
                    dp[i] = dp[j] + 1
                    prev_idx[i] = j
            if dp[i] >= dp[best_i]:
                best_i = i
        cur = best_i
        while cur != -1:
            anchor_indices.add(numbered[cur][0])
            cur = prev_idx[cur]

    result: list[int] = []
    prev = 0
    for idx, num in enumerate(orig_nums):
        if idx in anchor_indices and num is not None and num > prev:
            new_num = num
        else:
            new_num = prev + 1
        result.append(new_num)
        prev = new_num
    return result


class ReorderListWidget(QListWidget):
    reordered = Signal()

    def dropEvent(self, event):
        super().dropEvent(event)
        QTimer.singleShot(0, self.reordered.emit)


class CollectionReorderDialog(QDialog):
    def __init__(self, parent, rows_data: list[tuple[str, int | None, str, str]], *, default_mode: str = "bump"):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self.resize(660, 560)
        self._mode = default_mode if default_mode in ("bump", "compact") else "bump"
        self._updates: dict[str, str] = {}

        c = current_colors()
        app = QApplication.instance()
        mat = app.property("studio_material") if app else "solid"
        panel_bg = with_alpha(c["card"], 242 if mat != "solid" else 255).name(QColor.NameFormat.HexArgb)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 26)
        self._panel = QFrame(self)
        self._panel.setObjectName("reorderDialogPanel")
        self._panel.setStyleSheet(
            f"QFrame#reorderDialogPanel {{ background-color: {panel_bg}; border: 1px solid {c['card_line']}; border-radius: 18px; }}"
            f"QLabel#reorderEyebrow {{ color: {c['caption']}; font-size: 9pt; font-weight: 700; }}"
            f"QLabel#reorderTitle {{ color: {c['ink']}; font-size: 13pt; font-weight: 700; }}"
            f"QLabel#reorderStat {{ color: {c['label']}; font-size: 9.2pt; }}"
            f"QListWidget#reorderList {{ background: {c['subtle']}; color: {c['ink']}; border: 1px solid {c['card_line']}; border-radius: 12px; padding: 6px; font-size: 9.6pt; outline: none; }}"
            f"QListWidget#reorderList::item {{ padding: 7px 10px; border-radius: 8px; margin: 1px 0; }}"
            f"QListWidget#reorderList::item:selected {{ background: {c['accent_soft']}; color: {c['ink']}; border: 1px solid {c['row_active_line']}; }}"
            f"QListWidget#reorderList::item:hover {{ background: {c['row']}; }}"
        )
        outer.addWidget(self._panel)

        v = QVBoxLayout(self._panel)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)

        tag = QLabel("DD WORKSHOP STUDIO  /  SMART COLLECTION REORDER")
        tag.setObjectName("reorderEyebrow")
        v.addWidget(tag)

        top = QHBoxLayout()
        title = QLabel("拖拽重排并自动重算序号")
        title.setObjectName("reorderTitle")
        top.addWidget(title)
        top.addStretch(1)
        self.mode_seg = SegmentedControl(
            (("bump", "仅顺延冲突"), ("compact", "1→N 连续重排")),
            self._mode, 232,
        )
        self.mode_seg.setFixedHeight(32)
        self.mode_seg.valueChanged.connect(self._on_mode_changed)
        top.addWidget(self.mode_seg)
        v.addLayout(top)

        self.stat_lbl = QLabel()
        self.stat_lbl.setObjectName("reorderStat")
        v.addWidget(self.stat_lbl)

        self.list_widget = ReorderListWidget()
        self.list_widget.setObjectName("reorderList")
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.reordered.connect(self._recalculate)
        for key, orig_num, base_title, raw_title in rows_data:
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, (key, orig_num, base_title, raw_title))
            self.list_widget.addItem(it)
        v.addWidget(self.list_widget, 1)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        up_btn = SmoothButton("上移"); up_btn.setFixedWidth(74); up_btn.clicked.connect(lambda: self._nudge(-1))
        dn_btn = SmoothButton("下移"); dn_btn.setFixedWidth(74); dn_btn.clicked.connect(lambda: self._nudge(1))
        cancel_btn = SmoothButton("取消"); cancel_btn.setFixedWidth(92); cancel_btn.clicked.connect(self.reject)
        self.apply_btn = SmoothButton("应用新序号", "primary"); self.apply_btn.setFixedWidth(122); self.apply_btn.clicked.connect(self.accept)
        btns.addWidget(up_btn); btns.addWidget(dn_btn); btns.addStretch(1)
        btns.addWidget(cancel_btn); btns.addWidget(self.apply_btn)
        v.addLayout(btns)

        self._recalculate()
        self._entrance = QPropertyAnimation(self, b"windowOpacity", self)
        self._entrance.setDuration(motion_duration(220))
        self._entrance.setEasingCurve(mac_curve())
        self._entrance.setStartValue(0.0); self._entrance.setEndValue(1.0)
        QTimer.singleShot(0, self._start_entrance)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QRectF(self._panel.geometry())
        for i in range(10, 0, -1):
            p.setPen(QPen(QColor(0, 0, 0, round(2.6 if i > 6 else 4.2)), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(g.adjusted(-i * 1.4, -i * 1.0, i * 1.4, i * 1.8), 18 + i, 18 + i)

    def _start_entrance(self):
        if self.parentWidget() is not None:
            c = self.parentWidget().mapToGlobal(self.parentWidget().rect().center())
            self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)
        self.setWindowOpacity(0.0)
        self._entrance.start()

    def _on_mode_changed(self, mode: str):
        self._mode = mode
        self._recalculate()

    def _nudge(self, delta: int):
        row = self.list_widget.currentRow()
        target = row + delta
        if row < 0 or not (0 <= target < self.list_widget.count()):
            return
        it = self.list_widget.takeItem(row)
        self.list_widget.insertItem(target, it)
        self.list_widget.setCurrentRow(target)
        self._recalculate()

    def _recalculate(self):
        count = self.list_widget.count()
        meta = [self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(count)]
        new_nums = compute_reordered_numbers([m[1] for m in meta], self._mode)
        c = current_colors()
        changed_col = QColor(c["accent"])
        normal_col = QColor(c["ink"])
        self._updates.clear()
        for i, ((key, orig_num, base_title, raw_title), new_num) in enumerate(zip(meta, new_nums)):
            it = self.list_widget.item(i)
            new_title = raw_title if (orig_num == new_num) else f"{new_num} {base_title}".strip()
            if new_title != raw_title:
                self._updates[key] = new_title
                old_lbl = str(orig_num) if orig_num is not None else "无"
                it.setText(f"★ {old_lbl} → {new_num:<4} |  {base_title}")
                it.setForeground(changed_col)
            else:
                it.setText(f"   {new_num:<4}     |  {base_title}")
                it.setForeground(normal_col)
        n_upd = len(self._updates)
        self.stat_lbl.setText(
            f"直接拖动行或点击上下移调整顺序 · 共 {count} 项，本次将更新 {n_upd} 个 MOD 序号"
        )
        self.apply_btn.setEnabled(n_upd > 0)

    def result_updates(self) -> dict[str, str]:
        return dict(self._updates)
