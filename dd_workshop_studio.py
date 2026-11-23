"""Darkest Dungeon Workshop Studio - Frosted Glass Edition."""
from __future__ import annotations

from html import escape
from pathlib import Path
import re
import sys
import time

from PySide6.QtCore import Property, QEasingCurve, QEvent, QPropertyAnimation, QSettings, Qt, QTimer, QUrl, QVariantAnimation
from PySide6.QtGui import QAction, QColor, QDesktopServices, QGuiApplication, QIcon, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMenu, QPlainTextEdit, QProgressBar, QScrollArea, QSizePolicy,
    QSlider, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from archiver_core import DEFAULT_UPLOADER, DEFAULT_WORKSPACE, WORKSHOP_TAG_GROUPS, WORKSHOP_TAGS, WORKSHOP_URL, ModEntry, description_for, detect_workshop_uploader, human_bytes, load_entry, project_dir, save_draft, strip_title_index, upload_title_for
from library_widgets import CacheCleanupWorker, CollectionCheckBox, CollectionReorderDialog, ElidedNameLabel, ModCollectionHeader, ModRow, PipelineWorker
from mod_library_scan import LibraryGroup, discover_mod_groups
from studio_theme import (
    COLOR_PRESETS, PALETTES, SemanticLogHighlighter, blend, build_dynamic_palette, classify_log_role,
    current_colors, find_asset_file, find_brand_image, is_warm_accent, mac_curve, motion_duration, studio_font, with_alpha,
)
from studio_widgets import (
    AmbientRoot, BrandMark, BrandToggleButton, CaptionButton, ColorSwatch, GlassCard,
    ModPreviewArtwork, NavIndicator, NavItemButton, SegmentedControl, SmoothButton, AccentBadge, SmoothSlider, StatusPill, StudioColorDialog, StudioDialog, StudioMenu, ThemeTransition,
)
from win_backdrop import (
    IS_WIN32, apply_desktop_backdrop, backdrop_supported, handle_frameless_native_event,
    mica_supported, set_dwm_attribute, setup_dwm_frameless_window, win_build,
)


class StudioWindow(QMainWindow):
    NAV_EXPANDED_W = 196
    NAV_COLLAPSED_W = 58

    def __init__(self):
        super().__init__()
        self.setWindowTitle("moil的mod上传器")
        self.setAcceptDrops(True)
        if IS_WIN32:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        if (win_ico := find_asset_file("app.ico") or find_brand_image("blue")) is not None:
            self.setWindowIcon(QIcon(str(win_ico)))
        self.resize(1240, 820)
        self.setMinimumSize(940, 680)

        self.settings = QSettings("DDWorkshopStudio", "Studio")
        self.entries: dict[str, ModEntry] = {}
        self.rows: dict[str, ModRow] = {}
        self.collection_members: dict[str, list[str]] = {}
        self.collection_parents: dict[str, str | None] = {}
        self.collection_children: dict[str, list[str]] = {}
        self.collection_expanded: dict[str, bool] = {}
        self.collection_titles: dict[str, str] = {}
        self.collection_headers: dict[str, ModCollectionHeader] = {}
        self.collection_bodies: dict[str, QWidget] = {}
        self.collection_layouts: dict[str, QVBoxLayout] = {}
        self.collection_populated: set[str] = set()
        self._folder_groups: list[LibraryGroup] = []
        self._folder_expanded: dict[str, bool] = {}
        self._tag_expanded: dict[str, bool] = {}
        self.search_query = ""
        self.current_key: str | None = None
        self.multi_keys: set[str] = set()
        self.selection_anchor: str | None = None
        self.editor_loading = self._dwm_initialized = self._is_dragging = self._pipeline_busy = False
        self._draft_dirty = False
        self._pipeline_started_at = 0.0
        self.worker: PipelineWorker | None = None
        self.cache_worker: CacheCleanupWorker | None = None
        self._glass_level = 0.0
        self._glass_cards: list[GlassCard] = []
        self._morph_anim: QVariantAnimation | None = None
        self._glass_animation: QPropertyAnimation | None = None
        self._ambient_tick = 0
        self._live_log_role = "success"
        self._last_palette_key = None
        self._pending_pick_hex = None
        self._pick_timer = QTimer(self)
        self._pick_timer.setSingleShot(True)
        self._pick_timer.setInterval(16)
        self._theme_transition = None
        self._transition_anim = None
        self._cached_smooth_buttons = None
        self._entrance_done = False
        self._closing_anim_active = False
        self._close_ready = False
        self._entrance_anim = None
        self._exit_anim = None
        if motion_duration(260) > 0:
            self.setWindowOpacity(0.0)
        self._pick_timer.timeout.connect(self._flush_picked_color)

        self.appearance_mode = str(self.settings.value("appearance/mode", "system"))
        if self.appearance_mode not in {"system", "light", "dark"}:
            self.appearance_mode = "system"
        default_mat = "desktop" if backdrop_supported() else "liquid"
        self.material_mode = str(self.settings.value("appearance/material_mode", default_mat))
        if self.material_mode not in {"solid", "liquid", "desktop"} or (self.material_mode == "desktop" and not backdrop_supported()):
            self.material_mode = "liquid"
        self.backdrop_mode = str(self.settings.value("appearance/backdrop_mode", "acrylic"))
        if self.backdrop_mode not in {"mica", "acrylic"}:
            self.backdrop_mode = "acrylic"
        self.ambient_motion_on = self.settings.value("appearance/ambient_motion", True, type=bool)
        self.drag_assist = self.settings.value("appearance/drag_assist", False, type=bool)
        self.nav_collapsed = self.settings.value("layout/nav_collapsed", False, type=bool)
        self.strip_numbers = self.settings.value("upload/strip_collection_numbers", True, type=bool)
        self.strip_v2 = self.settings.value("upload/strip_v2_suffix", False, type=bool)
        self.library_view_mode = str(self.settings.value("layout/library_view_mode", "folder"))
        if self.library_view_mode not in {"folder", "collection", "tag_sort", "tag_group"}:
            self.library_view_mode = "folder"

        default_acc = "#C54A3E" if self.material_mode == "liquid" else "#4F8BFF"
        self.accent_hex = str(self.settings.value("appearance/accent_hex", default_acc)).upper()
        if not QColor(self.accent_hex).isValid():
            self.accent_hex = default_acc

        try:
            self.glass_strength = max(0, min(100, int(self.settings.value("appearance/glass_strength", 68))))
        except (ValueError, TypeError):
            self.glass_strength = 68

        self._current_theme = self.resolve_theme()
        self._active_palette_name = (self._current_theme + "_glass") if self.material_mode == "liquid" else self._current_theme
        self._current_palette = build_dynamic_palette(self._current_theme, self.material_mode, self.accent_hex)
        app = QApplication.instance()
        if app is not None:
            app.setProperty("studio_colors", self._current_palette)
            app.setProperty("studio_theme", self._current_theme)
            app.setProperty("studio_material", self.material_mode)

        self.build_ui()
        self.apply_theme(update_qss=True)
        self.set_glass_level(self.glass_strength / 100.0)
        self._glass_animation = QPropertyAnimation(self, b"glassLevel", self)
        self._glass_animation.setEasingCurve(mac_curve())

        self._ambient_timer = QTimer(self)
        self._ambient_timer.setInterval(125)
        self._ambient_timer.timeout.connect(self._ambient_frame)
        self._update_ambient_timer()

        if app is not None and hasattr(app.styleHints(), "colorSchemeChanged"):
            app.styleHints().colorSchemeChanged.connect(self.on_system_theme_changed)
        QTimer.singleShot(0, self.restore_splitters)
        self.draft_timer = QTimer(self)
        self.draft_timer.setSingleShot(True)
        self.draft_timer.setInterval(380)
        self.draft_timer.timeout.connect(self.save_current_draft)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(120)
        self.search_timer.timeout.connect(self._apply_search_filter)
        self._find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self._find_shortcut.activated.connect(self._focus_search_box)
        self.log_line("工作空间已就绪。选择包含多个 MOD 的目录，或直接拖入 / 添加单个 MOD 文件夹（Ctrl+F 快速搜索）。")
        if getattr(self, "_auto_detected_uploader", ""):
            self.log_line(f"✓ 已自动定位 Steam 工坊上传器：{self._auto_detected_uploader}")
        elif not Path(self.uploader_edit.text().strip()).is_file():
            self.log_line("⚠ 未检测到 steam_workshop_upload.exe，请在「外观与存储设置」中点击自动探测或手动指定。")

    def resolve_theme(self) -> str:
        if self.appearance_mode != "system":
            return self.appearance_mode
        try:
            if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark:
                return "dark"
        except (AttributeError, RuntimeError):
            pass
        return "light"

    def showEvent(self, event):
        super().showEvent(event)
        if IS_WIN32 and not self._dwm_initialized:
            setup_dwm_frameless_window(self)
            self._dwm_initialized = True
        self._sync_windows_backdrop()
        self._update_ambient_timer()
        QTimer.singleShot(0, lambda: self.nav_indicator.track(self.nav_buttons[self.stack.currentIndex()], animated=False))
        if not self._entrance_done:
            self._entrance_done = True
            QTimer.singleShot(0, self._play_entrance)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._update_ambient_timer()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "max_btn"):
            self.max_btn.set_maximized(self.isMaximized())
        if event.type() in (QEvent.Type.ActivationChange, QEvent.Type.WindowStateChange):
            if hasattr(self, "_ambient_timer"):
                QTimer.singleShot(0, self._update_ambient_timer)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "nav_indicator"):
            QTimer.singleShot(0, self.nav_indicator.snap)

    def _on_drag_state_changed(self, dragging: bool):
        if self._is_dragging == dragging: return
        self._is_dragging = dragging
        if self.drag_assist and not mica_supported() and self.material_mode == "desktop":
            if dragging:
                self._sync_windows_backdrop()
                self.centralWidget().repaint()
            else:
                QTimer.singleShot(35, self._restore_backdrop_after_drag)

    def _restore_backdrop_after_drag(self):
        if not self._is_dragging and self.material_mode == "desktop":
            self._sync_windows_backdrop()
            self.centralWidget().update()

    def nativeEvent(self, eventType, message):
        res = handle_frameless_native_event(self, eventType, message, titlebar_height=46, on_drag_state_changed=self._on_drag_state_changed)
        return res if res is not None else super().nativeEvent(eventType, message)

    def _toggle_maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _update_ambient_timer(self):
        timer = getattr(self, "_ambient_timer", None)
        if timer is None: return
        enabled = (
            self.ambient_motion_on and self.glass_strength > 0
            and not self._pipeline_busy and self.isVisible() and not self.isMinimized()
            and self.isActiveWindow() and motion_duration(100) > 0
        )
        if enabled and not timer.isActive(): timer.start()
        elif not enabled and timer.isActive(): timer.stop()

    def _ambient_frame(self):
        if isinstance(root := self.centralWidget(), AmbientRoot):
            self._ambient_tick = (self._ambient_tick + 1) % 4096
            root.set_motion_phase(self._ambient_tick * 0.021)

    def _sync_windows_backdrop(self):
        desired = (self.material_mode == "desktop") and backdrop_supported()
        theme = self.resolve_theme()
        c = getattr(self, "_current_palette", PALETTES[self._active_palette_name])
        tint = QColor(18, 22, 34, 88) if theme == "dark" else QColor(246, 248, 252, 115)
        kind = apply_desktop_backdrop(
            self, enabled=desired, mode=self.backdrop_mode if mica_supported() else "acrylic",
            dark=(theme == "dark"), tint=tint, dragging=(self._is_dragging and self.drag_assist),
        )
        if win_build() >= 22000:
            if self.material_mode != "solid":
                border = QColor("#74533B" if (self.material_mode == "liquid" and theme == "dark") else (
                    "#C3A27A" if self.material_mode == "liquid" else c["card_line"]
                ))
                set_dwm_attribute(self, 34, (border.blue() << 16) | (border.green() << 8) | border.red())
            else:
                set_dwm_attribute(self, 34, 0xFFFFFFFF)
        if isinstance(root := self.centralWidget(), AmbientRoot):
            root.material_mode = self.material_mode
            root.drag_opaque_fallback = (kind == "drag_paused")
            root.update()

    def build_ui(self):
        root = AmbientRoot(); root.setObjectName("root")
        root.sidebar_width = self.NAV_COLLAPSED_W if self.nav_collapsed else self.NAV_EXPANDED_W
        self.setCentralWidget(root)
        self.setStyleSheet("QMainWindow { background: transparent; }")

        outer_h = QHBoxLayout(root); outer_h.setContentsMargins(0, 0, 0, 0); outer_h.setSpacing(0)
        self.sidebar = QWidget(); self.sidebar.setFixedWidth(root.sidebar_width)
        nav_col = QVBoxLayout(self.sidebar); nav_col.setContentsMargins(10, 10, 10, 14); nav_col.setSpacing(6)

        nav_head = QHBoxLayout(); nav_head.setContentsMargins(1, 0, 1, 6); nav_head.setSpacing(8)
        self.menu_btn = BrandToggleButton(
            find_brand_image("red"), find_brand_image("blue"),
            initial_warmth=(1.0 if is_warm_accent(self.accent_hex) else 0.0)
        )
        self.menu_btn.setToolTip("点击图标 展开 / 收起导航栏")
        self.menu_btn.clicked.connect(self._toggle_sidebar)
        self.nav_brand_lbl = QLabel("DD Studio"); self.nav_brand_lbl.setObjectName("navBrand")
        nav_head.addWidget(self.menu_btn); nav_head.addWidget(self.nav_brand_lbl, 1)
        nav_col.addLayout(nav_head)

        self.nav_workbench = NavItemButton("workbench", "MOD 归档工作台")
        self.nav_logs = NavItemButton("logs", "运行日志与诊断")
        self.nav_settings = NavItemButton("settings", "外观与存储设置")
        self.nav_buttons = [self.nav_workbench, self.nav_logs, self.nav_settings]
        for idx, btn in enumerate(self.nav_buttons):
            btn.clicked.connect(lambda i=idx: self.switch_page(i))
        nav_col.addWidget(self.nav_workbench); nav_col.addWidget(self.nav_logs)
        nav_col.addStretch(1)
        self.nav_sort_audit = NavItemButton("sort", "一键排序查号")
        self.nav_sort_audit.setToolTip("一键排序查号：重排列表并检查 1–N 重号 / 漏号 / 未编号项")
        self.nav_sort_audit.setEnabled(False)
        self.nav_sort_audit.clicked.connect(self.sort_and_audit_numbers)
        nav_col.addWidget(self.nav_sort_audit)
        nav_col.addWidget(self.nav_settings)

        self.nav_indicator = NavIndicator(self.sidebar); self.nav_indicator.raise_()
        outer_h.addWidget(self.sidebar)

        right_wrap = QWidget(); right_col = QVBoxLayout(right_wrap)
        right_col.setContentsMargins(18, 6, 16, 10); right_col.setSpacing(8)

        title_strip = QHBoxLayout(); title_strip.setContentsMargins(2, 2, 0, 0); title_strip.setSpacing(10)
        self.page_heading = QLabel(); self.page_heading.setObjectName("pageTitle")
        self.page_subtitle = QLabel("moil的mod上传器 · PRIVATE ARCHIVE"); self.page_subtitle.setObjectName("subtitle")
        tcol = QVBoxLayout(); tcol.setSpacing(1); tcol.addWidget(self.page_heading); tcol.addWidget(self.page_subtitle)
        title_strip.addLayout(tcol, 1)

        if IS_WIN32:
            self.min_btn, self.max_btn, self.close_btn = CaptionButton("min"), CaptionButton("max"), CaptionButton("close")
            self.min_btn.clicked.connect(self.showMinimized)
            self.max_btn.clicked.connect(self._toggle_maximize)
            self.close_btn.clicked.connect(self.close)
            wbtns = QHBoxLayout(); wbtns.setSpacing(2); wbtns.setAlignment(Qt.AlignmentFlag.AlignTop)
            for b in (self.min_btn, self.max_btn, self.close_btn): wbtns.addWidget(b)
            title_strip.addLayout(wbtns)
        right_col.addLayout(title_strip)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_workbench_page())
        self.stack.addWidget(self._build_logs_page())
        self.stack.addWidget(self._build_settings_page())
        right_col.addWidget(self.stack, 1)
        outer_h.addWidget(right_wrap, 1)

        self._nav_anim = QPropertyAnimation(self, b"sidebarWidthProp", self)
        self._nav_anim.setDuration(motion_duration(240)); self._nav_anim.setEasingCurve(mac_curve())
        self._apply_sidebar_collapsed_visuals(self.nav_collapsed)
        for _w in (self.search_edit, self.title_edit, self.note_edit, self.description, self.log_view, self.uploader_edit, self.workspace_edit):
            _w.setAcceptDrops(False)
        self.switch_page(0); self.enable_editor(False)

    def _build_workbench_page(self) -> QWidget:
        page = QWidget(); v = QVBoxLayout(page); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(7)
        action_card = GlassCard(); self._glass_cards.append(action_card)
        bar = QHBoxLayout(action_card); bar.setContentsMargins(12, 8, 12, 8); bar.setSpacing(6)
        self.scan_button = SmoothButton("扫描 MOD 目录", "primary"); self.scan_button.setMinimumWidth(108); self.scan_button.clicked.connect(self.scan_folder)
        self.add_button = SmoothButton("添加单个 MOD"); self.add_button.setMinimumWidth(102); self.add_button.clicked.connect(self.add_single)
        self.count_label = QLabel("尚未选择 MOD"); self.count_label.setObjectName("dimText")
        self.prepare_btn = SmoothButton("仅生成归档"); self.prepare_btn.setMinimumWidth(90); self.prepare_btn.clicked.connect(lambda: self.start_pipeline(False))
        self.upload_btn = SmoothButton("归档上传 0", "primary"); self.upload_btn.setMinimumWidth(116); self.upload_btn.clicked.connect(lambda: self.start_pipeline(True))
        self.stop_btn = SmoothButton("停止后续"); self.stop_btn.setMinimumWidth(80); self.stop_btn.setEnabled(False); self.stop_btn.clicked.connect(self.request_stop)
        self.update_check = QCheckBox("允许更新"); self.update_check.setToolTip("允许更新已有工坊 ID 的项目 / 断点重试")
        self.status_text = StatusPill("READY"); self.status_text.setFixedSize(94, 30)
        for w in (self.scan_button, self.add_button): bar.addWidget(w)
        bar.addSpacing(4); bar.addWidget(self.count_label); bar.addStretch(1)
        bar.addWidget(self.update_check); bar.addSpacing(4)
        for w in (self.prepare_btn, self.upload_btn, self.stop_btn, self.status_text): bar.addWidget(w)
        v.addWidget(action_card)

        left = GlassCard(); self._glass_cards.append(left); left.setMinimumWidth(250)
        lcol = QVBoxLayout(left); lcol.setContentsMargins(14, 12, 14, 10); lcol.setSpacing(8)
        lh = QHBoxLayout(); lt = QLabel("MOD LIBRARY"); lt.setObjectName("eyebrow"); lh.addWidget(lt); lh.addStretch()
        self.pick_all = CollectionCheckBox("全选"); self.pick_all.setTristate(True); self.pick_all.stateChanged.connect(self.toggle_all)
        lh.addWidget(self.pick_all); lcol.addLayout(lh)
        self.library_mode_selector = SegmentedControl(
            (("folder", "目录"), ("collection", "合集序"), ("tag_sort", "标签序"), ("tag_group", "标签组")),
            self.library_view_mode, 234,
        )
        self.library_mode_selector.setMinimumSize(180, 30)
        self.library_mode_selector.setMaximumSize(16777215, 30)
        self.library_mode_selector.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.library_mode_selector.valueChanged.connect(self.on_library_view_mode_changed)
        lcol.addWidget(self.library_mode_selector)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索标题 / 目录 / ID / 标签...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumHeight(30)
        self.search_edit.textChanged.connect(lambda _: self.search_timer.start())
        lcol.addWidget(self.search_edit)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); scroll.setObjectName("listScroll")
        self.list_container = QWidget(); self.list_container.setObjectName("listInner")
        self.list_layout = QVBoxLayout(self.list_container); self.list_layout.setContentsMargins(0, 0, 4, 0); self.list_layout.setSpacing(6); self.list_layout.addStretch(1)
        scroll.setWidget(self.list_container); lcol.addWidget(scroll, 1)

        sa = QHBoxLayout(); sa.setContentsMargins(0, 0, 0, 0); sa.setSpacing(6)
        self.list_hint = QLabel("0 项"); self.list_hint.setObjectName("libraryStatPill")
        self.list_hint.setAlignment(Qt.AlignmentFlag.AlignCenter); self.list_hint.setMinimumHeight(32); self.list_hint.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        sa.addWidget(self.list_hint, 1)
        self.check_selected_button = SmoothButton("勾选", "library_check")
        self.uncheck_selected_button = SmoothButton("排除", "library_exclude")
        self.clear_library_button = SmoothButton("清除", "library_clear")
        for b in (self.check_selected_button, self.uncheck_selected_button, self.clear_library_button):
            b.setMinimumSize(0, 32); b.setMaximumHeight(32); b.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed); sa.addWidget(b, 1)
        self.check_selected_button.clicked.connect(lambda: self.set_highlighted_checked(True))
        self.uncheck_selected_button.clicked.connect(lambda: self.set_highlighted_checked(False))
        self.clear_library_button.clicked.connect(self.clear_library); lcol.addLayout(sa)

        self.editor_card = GlassCard(); self._glass_cards.append(self.editor_card); self.editor_card.setMinimumWidth(425)
        eo = QVBoxLayout(self.editor_card); eo.setContentsMargins(6, 6, 4, 6)
        self.editor_scroll = QScrollArea(); self.editor_scroll.setObjectName("editorScroll"); self.editor_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.editor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); self.editor_scroll.setWidgetResizable(True)
        eo.addWidget(self.editor_scroll)

        ef = QWidget(); ef.setObjectName("editorInner")
        el = QVBoxLayout(ef); el.setContentsMargins(12, 6, 12, 6); el.setSpacing(5)
        dh = QHBoxLayout(); dhl = QLabel("MOD DETAILS"); dhl.setObjectName("eyebrow"); dh.addWidget(dhl); dh.addStretch()
        self.id_badge = QLabel("等待选择"); self.id_badge.setObjectName("sourceBadge")
        self.id_badge.mousePressEvent = self._on_id_badge_clicked
        dh.addWidget(self.id_badge); el.addLayout(dh)

        ir = QHBoxLayout(); ir.setSpacing(10); self.icon_preview = ModPreviewArtwork(); self.icon_preview.setFixedSize(144, 112); ir.addWidget(self.icon_preview)
        idl = QVBoxLayout(); idl.setSpacing(3)
        ih = QLabel("PREVIEW ICON · 上传前检查"); ih.setObjectName("eyebrow"); idl.addWidget(ih)
        self.icon_dimensions = QLabel("尚未选择 MOD"); self.icon_dimensions.setObjectName("fieldLabel"); idl.addWidget(self.icon_dimensions)
        self.icon_size_label = QLabel("文件大小：—"); self.icon_size_label.setObjectName("dimText"); idl.addWidget(self.icon_size_label)
        self.icon_status = QLabel("原图只读 · 不改变源文件"); self.icon_status.setObjectName("previewStatus"); self.icon_status.setWordWrap(True); idl.addWidget(self.icon_status)
        idl.addStretch(1)
        ia = QHBoxLayout(); ia.setSpacing(6)
        self.icon_open_button = SmoothButton("查看原图"); self.icon_open_button.setFixedWidth(80); self.icon_open_button.setMinimumHeight(28); self.icon_open_button.setEnabled(False)
        self.icon_open_button.clicked.connect(self.open_preview_image)
        self.icon_reload_button = SmoothButton("刷新"); self.icon_reload_button.setFixedWidth(56); self.icon_reload_button.setMinimumHeight(28); self.icon_reload_button.setEnabled(False)
        self.icon_reload_button.clicked.connect(self.reload_preview_image)
        ia.addWidget(self.icon_open_button); ia.addWidget(self.icon_reload_button); ia.addStretch(1); idl.addLayout(ia)
        ir.addLayout(idl)

        tags_box = QFrame(); tags_box.setObjectName("tagsBox")
        tb_lay = QVBoxLayout(tags_box); tb_lay.setContentsMargins(9, 6, 9, 6); tb_lay.setSpacing(2)
        tr = QHBoxLayout(); tr.setSpacing(6)
        tl_hdr = QLabel("STEAM TAGS · 工坊标签"); tl_hdr.setObjectName("eyebrow"); tr.addWidget(tl_hdr); tr.addStretch()
        self.tags_counter = QLabel("未选标签"); self.tags_counter.setObjectName("dimText"); tr.addWidget(self.tags_counter); tb_lay.addLayout(tr)
        tags_grid = QGridLayout(); tags_grid.setContentsMargins(0, 1, 0, 0); tags_grid.setHorizontalSpacing(6); tags_grid.setVerticalSpacing(2)
        self.tag_checks: dict[str, QCheckBox] = {}
        row_idx = 0
        for grp_name, grp_tags in WORKSHOP_TAG_GROUPS:
            gl = QLabel(grp_name); gl.setObjectName("dimText"); tags_grid.addWidget(gl, row_idx, 0, 1, 2); row_idx += 1
            for i, tag_name in enumerate(grp_tags):
                cb = QCheckBox(tag_name)
                cb.toggled.connect(self.editor_changed)
                self.tag_checks[tag_name] = cb
                tags_grid.addWidget(cb, row_idx + i // 2, i % 2)
            row_idx += (len(grp_tags) + 1) // 2
        tb_lay.addLayout(tags_grid); tb_lay.addStretch(1)
        ir.addWidget(tags_box, 1); el.addLayout(ir)

        tr_title = QHBoxLayout()
        tl = QLabel("工坊标题"); tl.setObjectName("fieldLabel"); tr_title.addWidget(tl)
        self.upload_title_hint = ElidedNameLabel(""); self.upload_title_hint.setObjectName("dimText")
        tr_title.addSpacing(8); tr_title.addWidget(self.upload_title_hint, 1)
        self.strip_num_check = QCheckBox("上传时筛除序号")
        self.strip_num_check.setToolTip("仅在本地保留开头的 1–1000 合集序号及注释中的序号引用，生成上传 XML 与上传至 Steam 时自动筛除")
        self.strip_num_check.setChecked(self.strip_numbers)
        self.strip_num_check.toggled.connect(self.on_strip_numbers_toggled)
        tr_title.addWidget(self.strip_num_check)
        self.strip_v2_check = QCheckBox("去除 V2 后缀")
        self.strip_v2_check.setToolTip("上传及预览时自动去除标题与注释中独立的 V2/v2 后缀（不影响 V1.65、v2.1 等版本号）")
        self.strip_v2_check.setChecked(self.strip_v2)
        self.strip_v2_check.toggled.connect(self.on_strip_v2_toggled)
        tr_title.addWidget(self.strip_v2_check); el.addLayout(tr_title)
        self.title_edit = QLineEdit(); self.title_edit.setMinimumHeight(32); self.title_edit.setPlaceholderText("选择 MOD 后编辑标题")
        self.title_edit.textChanged.connect(self.editor_changed); el.addWidget(self.title_edit)

        oh = QLabel("原工坊来源 · 自动检测"); oh.setObjectName("fieldLabel"); el.addWidget(oh)
        self.origin_label = QLabel("未选中 MOD"); self.origin_label.setObjectName("originArea"); self.origin_label.setWordWrap(True)
        self.origin_label.setMinimumHeight(32); self.origin_label.setOpenExternalLinks(True)
        self.origin_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction); el.addWidget(self.origin_label)

        nr = QHBoxLayout(); nl = QLabel("专属注释 · 可自由编辑"); nl.setObjectName("fieldLabel"); nr.addWidget(nl); nr.addStretch()
        self.note_counter = QLabel("0 字"); self.note_counter.setObjectName("dimText"); nr.addWidget(self.note_counter); el.addLayout(nr)
        self.note_edit = QPlainTextEdit(); self.note_edit.setPlaceholderText("例如：请将本 MOD 排在其他相关人物皮肤 MOD 的上方……")
        self.note_edit.setFixedHeight(72); self.note_edit.setTabChangesFocus(True); self.note_edit.textChanged.connect(self.editor_changed); el.addWidget(self.note_edit)

        dr = QHBoxLayout(); ph = QLabel("最终工坊描述 · 实时预览"); ph.setObjectName("fieldLabel"); dr.addWidget(ph); dr.addStretch()
        self.preview_meta = QLabel("PRIVATE · ENGLISH"); self.preview_meta.setObjectName("dimText"); dr.addWidget(self.preview_meta); el.addLayout(dr)
        self.description = QPlainTextEdit(); self.description.setReadOnly(True); self.description.setObjectName("previewEdit")
        self.description.setMinimumHeight(78); el.addWidget(self.description, 1)
        self.editor_scroll.setWidget(ef)
        QTimer.singleShot(0, lambda: self.editor_scroll.verticalScrollBar().setValue(0))

        self.editor_pulse = QPropertyAnimation(self.editor_card, b"selectionPulse", self)
        self.editor_pulse.setDuration(motion_duration(360)); self.editor_pulse.setEasingCurve(mac_curve())

        self.columns_splitter = QSplitter(Qt.Orientation.Horizontal); self.columns_splitter.setObjectName("columnsSplitter")
        self.columns_splitter.setChildrenCollapsible(False); self.columns_splitter.setHandleWidth(10)
        self.columns_splitter.addWidget(left); self.columns_splitter.addWidget(self.editor_card)
        self.columns_splitter.setStretchFactor(0, 0); self.columns_splitter.setStretchFactor(1, 1); self.columns_splitter.setSizes([315, 680])
        v.addWidget(self.columns_splitter, 1)

        fc = GlassCard(); fc.setFixedHeight(36); self._glass_cards.append(fc)
        fv = QVBoxLayout(fc); fv.setContentsMargins(14, 0, 14, 0); fv.setSpacing(0)
        self.progress = QProgressBar(); self.progress.setFixedHeight(3); self.progress.setRange(0, 100); self.progress.setTextVisible(False)
        self.progress_anim = QPropertyAnimation(self.progress, b"value", self); self.progress_anim.setDuration(motion_duration(430)); self.progress_anim.setEasingCurve(mac_curve())

        log_row = QHBoxLayout(); log_row.setContentsMargins(0, 0, 0, 0); log_row.setSpacing(8)
        self.live_log_lbl = ElidedNameLabel("工作空间已就绪。选择包含多个 MOD 的目录，或直接添加单个 MOD 文件夹。")
        self.live_log_lbl.setObjectName("dimText"); self.live_log_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.live_log_lbl.setToolTip("单击跳转到「运行日志与诊断」查看完整实时流"); self.live_log_lbl.mousePressEvent = lambda e: self.switch_page(1)
        self.log_jump_hint = QLabel("诊断中心 ↗"); self.log_jump_hint.setObjectName("dimText")
        self.log_jump_hint.setCursor(Qt.CursorShape.PointingHandCursor); self.log_jump_hint.setToolTip("点击展开完整活动日志与错误诊断")
        self.log_jump_hint.mousePressEvent = lambda e: self.switch_page(1)
        log_row.addWidget(self.live_log_lbl, 1); log_row.addWidget(self.log_jump_hint)
        fv.addWidget(self.progress); fv.addLayout(log_row); v.addWidget(fc)
        return page

    def _build_logs_page(self) -> QWidget:
        page = QWidget(); v = QVBoxLayout(page); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(8)
        tc = GlassCard(); self._glass_cards.append(tc); tr = QHBoxLayout(tc); tr.setContentsMargins(14, 8, 14, 8); tr.setSpacing(8)
        tr.addWidget(QLabel("完整活动记录与 Steam 工坊诊断输出")); tr.addStretch(1)
        b_ws = SmoothButton("打开归档工作区"); b_ws.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.workspace()))))
        b_cur = SmoothButton("当前 MOD 归档目录"); b_cur.clicked.connect(self._open_current_project_dir)
        b_cp = SmoothButton("复制日志"); b_cp.clicked.connect(self._copy_logs)
        b_cl = SmoothButton("清空视图"); b_cl.clicked.connect(lambda: self.log_view.clear())
        for b in (b_ws, b_cur, b_cp, b_cl): tr.addWidget(b)
        v.addWidget(tc)

        lc = GlassCard(); self._glass_cards.append(lc); lv = QVBoxLayout(lc); lv.setContentsMargins(14, 12, 14, 12); lv.setSpacing(8)
        hd = QHBoxLayout(); eb = QLabel("ACTIVITY LOG"); eb.setObjectName("eyebrow"); hd.addWidget(eb); hd.addStretch(1)
        ht = QLabel("保留最近 1200 行 · 自动分色高亮错误、进度与工坊 ID"); ht.setObjectName("dimText"); hd.addWidget(ht); lv.addLayout(hd)
        self.log_view = QPlainTextEdit(); self.log_view.setReadOnly(True); self.log_view.setObjectName("logs")
        self.log_view.document().setMaximumBlockCount(1200)
        self.log_highlighter = SemanticLogHighlighter(self.log_view.document(), current_colors())
        lv.addWidget(self.log_view, 1); v.addWidget(lc, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget(); v = QVBoxLayout(page); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(10)
        mc_card = GlassCard(); self._glass_cards.append(mc_card); mc = QVBoxLayout(mc_card); mc.setContentsMargins(18, 14, 18, 14); mc.setSpacing(12)
        s1 = QLabel("外观主题与材质渲染引擎"); s1.setObjectName("eyebrow"); mc.addWidget(s1)

        rt = QHBoxLayout(); rt.addWidget(QLabel("界面主题（跟随系统、浅色或深色）")); rt.addStretch(1)
        self.theme_selector = SegmentedControl((("system", "跟随系统"), ("light", "浅色"), ("dark", "深色")), self.appearance_mode, 234)
        self.theme_selector.valueChanged.connect(self.change_theme_mode); rt.addWidget(self.theme_selector); mc.addLayout(rt)

        rm = QHBoxLayout(); ml = QVBoxLayout(); ml.setSpacing(2)
        ml.addWidget(QLabel("材质引擎（三者严格互斥，互不叠加糊底）"))
        mh = QLabel("经典纯色：实色高对比  |  液体玻璃：应用内红金流光  |  桌面亚克力：真实透出壁纸与窗口"); mh.setObjectName("dimText")
        ml.addWidget(mh); rm.addLayout(ml, 1)
        self.material_selector = SegmentedControl(
            (("solid", "经典纯色"), ("liquid", "液体玻璃"), ("desktop", "桌面毛玻璃" if mica_supported() else "桌面亚克力")),
            self.material_mode, 286,
        )
        self.material_selector.valueChanged.connect(self.on_material_changed); rm.addWidget(self.material_selector); mc.addLayout(rm)

        rs = QHBoxLayout(); self.strength_caption = QLabel("通透度 / 光晕强度（越高越透出桌面或流光越浓）"); rs.addWidget(self.strength_caption); rs.addStretch(1)
        self.glass_slider = SmoothSlider(Qt.Orientation.Horizontal); self.glass_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.glass_slider.setRange(0, 100); self.glass_slider.setValue(self.glass_strength); self.glass_slider.setFixedWidth(210)
        self.glass_slider.valueChanged.connect(self.on_glass_strength_changed)
        self.glass_percent = QLabel(f"{self.glass_strength}%"); self.glass_percent.setObjectName("dimText"); self.glass_percent.setFixedWidth(42)
        rs.addWidget(self.glass_slider); rs.addWidget(self.glass_percent); mc.addLayout(rs)

        rc = QHBoxLayout(); rc.setSpacing(8)
        rc.addWidget(QLabel("主题色调与自由调色（联动红金 / 钴蓝图标）")); rc.addStretch(1)
        self.color_swatches: list[ColorSwatch] = []
        for hx, tip in COLOR_PRESETS:
            sw = ColorSwatch(hx, tip)
            sw.set_active(hx.upper() == self.accent_hex)
            sw.picked.connect(self._set_accent_hex)
            self.color_swatches.append(sw); rc.addWidget(sw)
        self.accent_hex_lbl = AccentBadge(self.accent_hex)
        self.pick_color_btn = SmoothButton("自定义取色..."); self.pick_color_btn.setMinimumHeight(30); self.pick_color_btn.setFixedWidth(104)
        self.pick_color_btn.clicked.connect(self._open_color_picker)
        rc.addWidget(self.accent_hex_lbl); rc.addWidget(self.pick_color_btn); mc.addLayout(rc)

        ro = QHBoxLayout()
        self.motion_toggle = QCheckBox("光球微动态呼吸（以 8 FPS 轻缓漂移极光氛围）")
        self.motion_toggle.setChecked(self.ambient_motion_on); self.motion_toggle.toggled.connect(self.on_motion_toggled); ro.addWidget(self.motion_toggle)
        self.acrylic_prefer = QCheckBox("Win11 透底亚克力（取消则使用柔和云母）")
        self.acrylic_prefer.setChecked(self.backdrop_mode == "acrylic"); self.acrylic_prefer.toggled.connect(self.on_backdrop_mode_toggled)
        ro.addWidget(self.acrylic_prefer)
        self.drag_assist_chk = QCheckBox("Win10 拖动防掉帧（拖动时临时暂停亚克力）")
        self.drag_assist_chk.setChecked(self.drag_assist); self.drag_assist_chk.toggled.connect(self.on_drag_assist_toggled)
        ro.addWidget(self.drag_assist_chk); ro.addStretch(1); mc.addLayout(ro)

        rp = QHBoxLayout(); rp.setSpacing(8); pl = QLabel("氛围预设："); pl.setObjectName("dimText"); rp.addWidget(pl)
        presets = [
            ("高透桌面亚克力", "desktop", 72, "#4F8BFF", True),
            ("沉稳桌面磨砂", "desktop", 38, "#4F8BFF", False),
            ("地牢红金流光", "liquid", 68, "#C54A3E", True),
            ("经典实色", "solid", 0, "#5965E9", False),
        ]
        for txt, m, st, acc, opt in presets:
            b = SmoothButton(txt); b.setMinimumHeight(32)
            b.clicked.connect(lambda mm=m, ss=st, aa=acc, oo=opt: self._apply_preset(mm, ss, aa, oo))
            rp.addWidget(b)
        rp.addStretch(1); mc.addLayout(rp); v.addWidget(mc_card)

        pc_card = GlassCard(); self._glass_cards.append(pc_card); pc = QVBoxLayout(pc_card); pc.setContentsMargins(18, 14, 18, 14); pc.setSpacing(8)
        s2 = QLabel("工具路径与归档工作空间"); s2.setObjectName("eyebrow"); pc.addWidget(s2)
        saved_uploader = str(self.settings.value("uploader", "")).strip()
        self._auto_detected_uploader = ""
        if not saved_uploader or not Path(saved_uploader).is_file():
            if (detected := detect_workshop_uploader()) is not None:
                saved_uploader = str(detected)
                self._auto_detected_uploader = saved_uploader
                self.settings.setValue("uploader", saved_uploader)
            elif not saved_uploader:
                saved_uploader = str(DEFAULT_UPLOADER)
        self.uploader_edit = QLineEdit(saved_uploader)
        self.workspace_edit = QLineEdit(str(self.settings.value("workspace", str(DEFAULT_WORKSPACE))))
        self.uploader_edit.editingFinished.connect(self.persist_settings); self.workspace_edit.editingFinished.connect(self.on_workspace_changed)
        auto_up = SmoothButton("自动探测"); auto_up.setFixedWidth(96)
        auto_up.clicked.connect(self.auto_detect_uploader)
        pc.addLayout(self.path_field("STEAM WORKSHOP UPLOADER", self.uploader_edit, self.browse_uploader, extra_button=auto_up))
        open_ws = SmoothButton("打开目录"); open_ws.setFixedWidth(96)
        open_ws.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.workspace()))))
        pc.addLayout(self.path_field("ARCHIVE WORKSPACE", self.workspace_edit, self.browse_workspace, extra_button=open_ws))
        v.addWidget(pc_card)

        cc_card = GlassCard(); self._glass_cards.append(cc_card); cc = QHBoxLayout(cc_card); cc.setContentsMargins(18, 12, 18, 12); cc.setSpacing(14)
        ct = QVBoxLayout(); ct.setSpacing(2)
        ctl = QLabel("安全回收已上传副本缓存（payload）"); ctl.setObjectName("fieldLabel")
        cd = QLabel("仅清理已确认 SUCCESS 的临时副本；原始 MOD、工坊 ID、upload.xml、注释与诊断日志永久保留。"); cd.setObjectName("dimText"); cd.setWordWrap(True)
        ct.addWidget(ctl); ct.addWidget(cd)
        self.cleanup_cache_button = SmoothButton("清理已上传缓存"); self.cleanup_cache_button.setFixedWidth(142)
        self.cleanup_cache_button.clicked.connect(self.confirm_cleanup_cache)
        cc.addLayout(ct, 1); cc.addWidget(self.cleanup_cache_button); v.addWidget(cc_card); v.addStretch(1)

        self._sync_material_controls_visibility()
        return page

    def switch_page(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons): btn.set_active(i == index)
        if hasattr(self, "nav_sort_audit"):
            self.nav_sort_audit.setVisible(index == 0)
        if hasattr(self, "nav_indicator"):
            self.nav_indicator.track(self.nav_buttons[index], animated=self.isVisible())
        self.page_heading.setText((
            "MOD 归档工坊（一键扫描、核对元数据与独立上传）",
            "运行日志与 Steam 工坊诊断中心",
            "外观材质、动态美学与存储设置",
        )[index])

    def get_sidebar_width_prop(self) -> int: return self.sidebar.width()
    def set_sidebar_width_prop(self, w: int):
        w = int(w); self.sidebar.setFixedWidth(w)
        if isinstance(root := self.centralWidget(), AmbientRoot): root.sidebar_width = w; root.update()
    sidebarWidthProp = Property(int, get_sidebar_width_prop, set_sidebar_width_prop)

    def _apply_sidebar_collapsed_visuals(self, collapsed: bool):
        self.nav_brand_lbl.setVisible(not collapsed)
        for btn in self.nav_buttons: btn.set_collapsed(collapsed)
        if hasattr(self, "nav_sort_audit"): self.nav_sort_audit.set_collapsed(collapsed)

    def _toggle_sidebar(self):
        self.nav_collapsed = not self.nav_collapsed
        self.settings.setValue("layout/nav_collapsed", self.nav_collapsed)
        self.settings.setValue("layout/library_view_mode", self.library_view_mode)
        self.settings.setValue("upload/strip_collection_numbers", self.strip_numbers)
        self.settings.setValue("upload/strip_v2_suffix", self.strip_v2)
        self._apply_sidebar_collapsed_visuals(self.nav_collapsed)
        self._nav_anim.stop(); self._nav_anim.setStartValue(self.sidebar.width())
        self._nav_anim.setEndValue(self.NAV_COLLAPSED_W if self.nav_collapsed else self.NAV_EXPANDED_W); self._nav_anim.start()

    def _sync_material_controls_visibility(self):
        d = (self.material_mode == "desktop")
        self.glass_slider.setEnabled(True)
        self.strength_caption.setEnabled(True)
        self.glass_percent.setEnabled(True)
        self.motion_toggle.setVisible(True)
        self.acrylic_prefer.setVisible(d and mica_supported())
        if hasattr(self, "drag_assist_chk"): self.drag_assist_chk.setVisible(d and not mica_supported())

    def on_material_changed(self, mat: str):
        if mat == "desktop" and not backdrop_supported():
            StudioDialog.information(self, "系统不支持", "桌面毛玻璃需要 Windows 10 (1803+) 或 Windows 11。")
            self.material_selector.set_value(self.material_mode, emit=False); return
        self.morph_appearance(target_mat=mat, duration=340)

    def _preview_accent_hex(self, hex_color: str):
        col = QColor(hex_color)
        if not col.isValid():
            return
        self.accent_hex = col.name().upper()
        if hasattr(self, "accent_hex_lbl"):
            self.accent_hex_lbl.setText(self.accent_hex)
        if hasattr(self, "menu_btn"):
            self.menu_btn.set_warmth(1.0 if is_warm_accent(self.accent_hex) else 0.0)
        self._current_palette = build_dynamic_palette(self.resolve_theme(), self.material_mode, self.accent_hex)
        QApplication.instance().setProperty("studio_colors", self._current_palette)
        self.fast_repaint_all(rehighlight_logs=False)

    def _flush_picked_color(self):
        if self._pending_pick_hex:
            self._preview_accent_hex(self._pending_pick_hex)

    def _set_accent_hex(self, hex_color: str, *, save: bool = True, animated: bool = True):
        col = QColor(hex_color)
        if not col.isValid(): return
        if animated and self.isVisible() and motion_duration(340) > 0:
            self.morph_appearance(target_accent=col.name().upper(), duration=340)
        else:
            self.accent_hex = col.name().upper()
            if save: self.settings.setValue("appearance/accent_hex", self.accent_hex)
            if hasattr(self, "accent_hex_lbl"): self.accent_hex_lbl.setText(self.accent_hex)
            if hasattr(self, "color_swatches"):
                for sw in self.color_swatches: sw.set_active(sw.hex_color == self.accent_hex)
            if hasattr(self, "menu_btn"):
                self.menu_btn.set_warmth(1.0 if is_warm_accent(self.accent_hex) else 0.0)
            self._current_palette = build_dynamic_palette(self.resolve_theme(), self.material_mode, self.accent_hex)
            QApplication.instance().setProperty("studio_colors", self._current_palette)
            self.apply_theme(update_qss=True)

    def _open_color_picker(self):
        old_hex = self.accent_hex
        dlg = StudioColorDialog(self, old_hex)
        def _on_live(col: QColor):
            if col.isValid():
                self._pending_pick_hex = col.name().upper()
                if not self._pick_timer.isActive(): self._pick_timer.start()
        dlg.colorChanged.connect(_on_live)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selectedColor().isValid():
            self._pick_timer.stop()
            self._pending_pick_hex = None
            self._set_accent_hex(dlg.selectedColor().name().upper(), save=True, animated=False)
        else:
            self._pick_timer.stop()
            self._pending_pick_hex = None
            self._set_accent_hex(old_hex, save=False, animated=True)

    def _apply_preset(self, mat: str, strength: int, accent: str, opt: bool):
        self.morph_appearance(
            target_mat=mat, target_strength=strength, target_accent=accent, target_opt=opt, duration=360
        )

    # ★ 60 FPS 零掉帧变色引擎：双色图标平滑交叉溶解，纯自绘图层无感重绘，收尾单次固化 QSS
    def _crossfade_update(self, apply_fn, duration: int = 220):
        cw = self.centralWidget()
        if cw is None or not self.isVisible() or motion_duration(duration) <= 0:
            apply_fn()
            return
        if self._transition_anim is not None:
            self._transition_anim.stop()
            self._transition_anim = None
        if self._theme_transition is not None:
            self._theme_transition.deleteLater()
            self._theme_transition = None
        snap = cw.grab()
        apply_fn()
        overlay = ThemeTransition(snap, cw)
        overlay.setGeometry(cw.rect())
        overlay.show()
        overlay.raise_()
        anim = QPropertyAnimation(overlay, b"opacityLevel", self)
        anim.setDuration(motion_duration(duration))
        anim.setEasingCurve(mac_curve())
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        def _cleanup():
            if self._theme_transition is overlay:
                self._theme_transition = None
            if self._transition_anim is anim:
                self._transition_anim = None
            overlay.deleteLater()
        anim.finished.connect(_cleanup)
        self._theme_transition = overlay
        self._transition_anim = anim
        anim.start()

    def morph_appearance(self, *, target_mat: str = None, target_strength: int = None,
                         target_accent: str = None, target_opt: bool = None, duration: int = 340):
        if hasattr(self, "_morph_anim") and self._morph_anim is not None:
            self._morph_anim.stop()

        if target_mat and target_mat != self.material_mode:
            prev_mat = self.material_mode
            def _apply_mat_switch():
                self.material_mode = target_mat
                self.settings.setValue("appearance/material_mode", target_mat)
                self.material_selector.set_value(target_mat, emit=False)
                if target_strength is not None:
                    self.glass_strength = int(target_strength)
                    self.settings.setValue("appearance/glass_strength", self.glass_strength)
                    self.glass_slider.blockSignals(True); self.glass_slider.setValue(self.glass_strength); self.glass_slider.blockSignals(False)
                    self.glass_percent.setText(f"{self.glass_strength}%")
                self.set_glass_level(self.glass_strength / 100.0)
                if target_accent is not None:
                    self.accent_hex = QColor(target_accent).name().upper()
                    self.settings.setValue("appearance/accent_hex", self.accent_hex)
                if target_opt is not None:
                    if self.material_mode == "desktop":
                        self.backdrop_mode = "acrylic" if target_opt else "mica"
                        self.settings.setValue("appearance/backdrop_mode", self.backdrop_mode)
                        self.acrylic_prefer.blockSignals(True); self.acrylic_prefer.setChecked(target_opt); self.acrylic_prefer.blockSignals(False)
                    elif self.material_mode == "liquid":
                        self.ambient_motion_on = target_opt
                        self.settings.setValue("appearance/ambient_motion", target_opt)
                        self.motion_toggle.blockSignals(True); self.motion_toggle.setChecked(target_opt); self.motion_toggle.blockSignals(False)
                if hasattr(self, "accent_hex_lbl"):
                    self.accent_hex_lbl.setText(self.accent_hex)
                if hasattr(self, "color_swatches"):
                    for sw in self.color_swatches:
                        sw.set_active(sw.hex_color == self.accent_hex)
                self._sync_material_controls_visibility()
                self._update_ambient_timer()
                if prev_mat == "desktop" and target_mat != "desktop":
                    self.apply_theme(update_qss=True)
                    if (cw := self.centralWidget()) is not None:
                        cw.repaint()
                    QTimer.singleShot(25, lambda: self.material_mode != "desktop" and self._sync_windows_backdrop())
                else:
                    self._sync_windows_backdrop()
                    self.apply_theme(update_qss=True)
            self._crossfade_update(_apply_mat_switch, duration=min(240, max(160, duration)))
            return

        start_col = QColor(self.accent_hex)
        end_col = QColor(target_accent if target_accent else self.accent_hex)
        start_st = self.glass_slider.value()
        end_st = target_strength if target_strength is not None else start_st
        start_w = 1.0 if is_warm_accent(self.accent_hex) else 0.0
        end_w = 1.0 if is_warm_accent(end_col.name()) else 0.0

        if target_mat and target_mat != self.material_mode:
            self.material_mode = target_mat
            self.settings.setValue("appearance/material_mode", target_mat)
            self.material_selector.set_value(target_mat, emit=False)

        if target_opt is not None:
            if self.material_mode == "desktop":
                self.backdrop_mode = "acrylic" if target_opt else "mica"
                self.settings.setValue("appearance/backdrop_mode", self.backdrop_mode)
                self.acrylic_prefer.blockSignals(True)
                self.acrylic_prefer.setChecked(target_opt)
                self.acrylic_prefer.blockSignals(False)
            elif self.material_mode == "liquid":
                self.ambient_motion_on = target_opt
                self.settings.setValue("appearance/ambient_motion", target_opt)
                self.motion_toggle.blockSignals(True)
                self.motion_toggle.setChecked(target_opt)
                self.motion_toggle.blockSignals(False)

        self._sync_material_controls_visibility()
        self._update_ambient_timer()
        self._sync_windows_backdrop()

        if duration <= 0 or motion_duration(duration) <= 0 or not self.isVisible():
            self.accent_hex = end_col.name().upper()
            self.glass_strength = end_st
            self.glass_slider.blockSignals(True); self.glass_slider.setValue(end_st); self.glass_slider.blockSignals(False)
            self.glass_percent.setText(f"{end_st}%")
            self.set_glass_level(end_st / 100.0)
            if hasattr(self, "menu_btn"): self.menu_btn.set_warmth(end_w)
            self._current_palette = build_dynamic_palette(self.resolve_theme(), self.material_mode, self.accent_hex)
            QApplication.instance().setProperty("studio_colors", self._current_palette)
            self.apply_theme(update_qss=True)
            return

        anim = QVariantAnimation(self)
        anim.setDuration(motion_duration(duration))
        anim.setEasingCurve(mac_curve())
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)

        def _tick(t: float):
            cur_col = blend(start_col, end_col, t)
            cur_hex = cur_col.name().upper()
            self._current_palette = build_dynamic_palette(self.resolve_theme(), self.material_mode, cur_hex)
            QApplication.instance().setProperty("studio_colors", self._current_palette)
            if hasattr(self, "accent_hex_lbl"): self.accent_hex_lbl.setText(cur_hex)

            cur_st = round(start_st + (end_st - start_st) * t)
            self.glass_slider.blockSignals(True); self.glass_slider.setValue(cur_st); self.glass_slider.blockSignals(False)
            self.glass_percent.setText(f"{cur_st}%")
            self.set_glass_level(cur_st / 100.0)

            cur_w = start_w + (end_w - start_w) * t
            if hasattr(self, "menu_btn"): self.menu_btn.set_warmth(cur_w)

            self.fast_repaint_all(rehighlight_logs=False)

        def _done():
            self._morph_anim = None
            self.accent_hex = end_col.name().upper()
            self.glass_strength = end_st
            self.settings.setValue("appearance/accent_hex", self.accent_hex)
            self.settings.setValue("appearance/glass_strength", self.glass_strength)
            if hasattr(self, "accent_hex_lbl"): self.accent_hex_lbl.setText(self.accent_hex)
            if hasattr(self, "color_swatches"):
                for sw in self.color_swatches: sw.set_active(sw.hex_color == self.accent_hex)
            self.apply_theme(update_qss=True)

        anim.valueChanged.connect(_tick)
        anim.finished.connect(_done)
        self._morph_anim = anim
        anim.start()

    def fast_repaint_all(self, *, rehighlight_logs: bool = True):
        if isinstance(root := self.centralWidget(), AmbientRoot): root.update()
        for card in self._glass_cards:
            if card.isVisible(): card.update()
        if self._cached_smooth_buttons is None:
            self._cached_smooth_buttons = self.findChildren(SmoothButton)
        for w in self._cached_smooth_buttons + self.nav_buttons + ([self.nav_sort_audit] if hasattr(self, "nav_sort_audit") else []) + [
            self.menu_btn, self.theme_selector, self.material_selector, self.library_mode_selector, self.status_text, self.icon_preview, self.nav_indicator, self.glass_slider, self.accent_hex_lbl
        ]:
            if w.isVisible(): w.update()
        for r in self.rows.values():
            if r.isVisible(): r.update()
        for h in self.collection_headers.values():
            if h.isVisible(): h.update()
        if rehighlight_logs:
            self._refresh_live_log_color()
            if hasattr(self, "log_highlighter"):
                self.log_highlighter.set_colors(self._current_palette)

    def on_motion_toggled(self, enabled: bool):
        self.ambient_motion_on = bool(enabled); self.settings.setValue("appearance/ambient_motion", self.ambient_motion_on); self._update_ambient_timer()

    def on_backdrop_mode_toggled(self, use_acrylic: bool):
        self.backdrop_mode = "acrylic" if use_acrylic else "mica"; self.settings.setValue("appearance/backdrop_mode", self.backdrop_mode); self._sync_windows_backdrop()

    def on_drag_assist_toggled(self, enabled: bool):
        self.drag_assist = bool(enabled); self.settings.setValue("appearance/drag_assist", self.drag_assist)

    def on_glass_strength_changed(self, value: int):
        self.glass_strength = int(value); self.glass_percent.setText(f"{value}%"); self.settings.setValue("appearance/glass_strength", value)
        self._update_ambient_timer(); self.animate_glass(value / 100.0, duration=120 if self.glass_slider.isSliderDown() else 280)

    def get_glass_level(self): return self._glass_level
    def set_glass_level(self, level):
        self._glass_level = min(1.0, max(0.0, float(level)))
        if isinstance(root := self.centralWidget(), AmbientRoot):
            root.glass_level = self._glass_level; root.material_mode = self.material_mode; root.update()
        for card in self._glass_cards:
            card.glass_level = self._glass_level; card.material_mode = self.material_mode; card.update()
    glassLevel = Property(float, get_glass_level, set_glass_level)

    def animate_glass(self, target: float, duration: int = 340):
        if self._glass_animation is None: self.set_glass_level(target); return
        self._glass_animation.stop(); self._glass_animation.setDuration(motion_duration(duration))
        self._glass_animation.setStartValue(self._glass_level); self._glass_animation.setEndValue(target); self._glass_animation.start()

    def change_theme_mode(self, mode: str):
        if mode in ("system", "light", "dark"):
            self.appearance_mode = mode; self.settings.setValue("appearance/mode", mode)
            self._crossfade_update(lambda: self.apply_theme(update_qss=True), duration=220)

    def on_system_theme_changed(self, _):
        if self.appearance_mode == "system": self.apply_theme(update_qss=True)

    def apply_theme(self, update_qss: bool = True):
        theme = self.resolve_theme()
        palette_name = f"{theme}_glass" if self.material_mode == "liquid" else theme
        self._current_theme, self._active_palette_name = theme, palette_name
        c = build_dynamic_palette(theme, self.material_mode, self.accent_hex)
        self._current_palette = c
        app = QApplication.instance()
        app.setProperty("studio_colors", c); app.setProperty("studio_theme", theme); app.setProperty("studio_material", self.material_mode)

        pal_key = (theme, self.material_mode)
        if self._last_palette_key != pal_key:
            self._last_palette_key = pal_key
            p = QPalette()
            for role, key in ((QPalette.ColorRole.Window, "background"), (QPalette.ColorRole.WindowText, "ink"),
                              (QPalette.ColorRole.Base, "input"), (QPalette.ColorRole.AlternateBase, "subtle"),
                              (QPalette.ColorRole.Text, "ink"), (QPalette.ColorRole.Button, "btn"),
                              (QPalette.ColorRole.ButtonText, "btn_text"), (QPalette.ColorRole.Highlight, "accent")):
                p.setColor(role, QColor(c[key]))
            p.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
            app.setPalette(p)

        is_dark = (theme == "dark")
        if self.material_mode == "desktop":
            in_bg = "rgba(255, 255, 255, 13)" if is_dark else "rgba(255, 255, 255, 165)"
            in_bd = "rgba(255, 255, 255, 28)" if is_dark else "rgba(15, 23, 42, 32)"
            sub_bg = "rgba(255, 255, 255, 9)" if is_dark else "rgba(255, 255, 255, 135)"
            row_bg = "rgba(255, 255, 255, 13)" if is_dark else "rgba(255, 255, 255, 145)"
            row_act = with_alpha(c["accent"], 46).name(QColor.NameFormat.HexArgb)
        elif self.material_mode == "liquid":
            in_bg, in_bd = with_alpha(c["input"], 215).name(QColor.NameFormat.HexArgb), c["card_line"]
            sub_bg = with_alpha(c["subtle"], 205).name(QColor.NameFormat.HexArgb)
            row_bg = with_alpha(c["row"], 210).name(QColor.NameFormat.HexArgb)
            row_act = with_alpha(c["row_active"], 225).name(QColor.NameFormat.HexArgb)
        else:
            in_bg, in_bd, sub_bg, row_bg, row_act = c["input"], c["card_line"], c["subtle"], c["row"], c["row_active"]

        if update_qss:
            self.stack.setStyleSheet(f"""
            QWidget#root {{ background: transparent; }} QFrame#card {{ background: transparent; border: none; }}
            QLabel {{ color: {c['label']}; font-size: 9.5pt; }}
            QLabel#pageTitle {{ font-size: 13.5pt; font-weight: 700; color: {c['ink']}; }}
            QLabel#navBrand {{ font-size: 10.5pt; font-weight: 700; color: {c['ink']}; }}
            QLabel#subtitle {{ font-size: 8.5pt; font-weight: 600; color: {c['caption']}; }}
            QLabel#libraryStatPill {{ background: {c['library_stat_bg']}; color: {c['library_stat_ink']}; border: 1px solid {c['library_stat_line']}; border-radius: 16px; font-size: 9pt; font-weight: 700; }}
            QLabel#eyebrow, QLabel#pathLabel {{ color: {c['muted']}; font-size: 8.8pt; font-weight: 700; }}
            QLabel#fieldLabel {{ color: {c['label']}; font-size: 9.8pt; font-weight: 600; }}
            QLabel#dimText, QLabel#rowSub {{ color: {c['caption']}; font-size: 8.8pt; }}
            QLabel#rowTitle {{ color: {c['ink']}; font-size: 9.8pt; font-weight: 600; }}
            QLabel#sourceBadge {{ background: {c['accent_soft']}; color: {c['ink']}; padding: 4px 10px; border-radius: 9px; font-size: 8.8pt; font-weight: 600; }}
            QLabel#originArea {{ color: {c['label']}; background: {sub_bg}; border: 1px solid {in_bd}; border-radius: 10px; padding: 8px 11px; font-size: 9.5pt; }}
            QFrame#tagsBox {{ background: {sub_bg}; border: 1px solid {in_bd}; border-radius: 10px; }}
            QFrame#tagsBox QCheckBox {{ font-size: 8.6pt; spacing: 5px; }}
            QLineEdit, QPlainTextEdit {{ color: {c['ink']}; selection-background-color: {c['highlight']}; background: {in_bg}; border: 1px solid {in_bd}; border-radius: 10px; padding: 7px 11px; font-size: 9.8pt; }}
            QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {c['accent']}; }}
            QPlainTextEdit#previewEdit {{ background: {sub_bg}; color: {c['label']}; border: 1px solid {in_bd}; }}
            QPlainTextEdit#logs {{ background: {sub_bg}; color: {c['log_text']}; border: 1px solid {in_bd}; font-family: 'Cascadia Mono', 'Consolas', 'Microsoft YaHei UI'; font-size: 9.5pt; }}
            QWidget#modCollectionChildren {{ background: transparent; border: none; }}
            QLabel#collectionArrow {{ color: {c['accent']}; font-size: 13pt; font-weight: 700; }}
            QLabel#collectionName {{ color: {c['ink']}; font-size: 9.8pt; font-weight: 650; }}
            QLabel#collectionSummary {{ color: {c['caption']}; font-size: 8.8pt; }}
            QFrame#modRow {{ border: 1px solid transparent; border-radius: 11px; background: {row_bg}; }}
            QFrame#modRowActive {{ border: 1px solid {c['row_active_line']}; border-radius: 11px; background: {row_act}; }}
            QCheckBox {{ color: {c['label']}; font-size: 9.2pt; spacing: 7px; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {in_bd}; border-radius: 5px; background: {in_bg}; }}
            QCheckBox::indicator:checked {{ background: {c['accent']}; border: 1px solid {c['accent']}; }}
            QCheckBox::indicator:hover {{ border: 2px solid {c['accent_hover']}; }}
            QScrollArea#listScroll, QWidget#listInner, QScrollArea#editorScroll, QWidget#editorInner, QSplitter#columnsSplitter {{ background: transparent; border: none; }}
            QSplitter::handle {{ background: transparent; }} QSplitter::handle:hover {{ background: {c['accent_soft']}; border-radius: 4px; }}
            QScrollBar:vertical {{ background: transparent; width: 7px; margin: 4px 0; }}
            QScrollBar::handle:vertical {{ background: {c['scroll']}; border-radius: 3px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QProgressBar {{ background: {in_bd}; border: none; border-radius: 2px; }} QProgressBar::chunk {{ background: {c['accent']}; border-radius: 2px; }}
            QSlider::groove:horizontal {{ height: 5px; border-radius: 2px; background: {in_bd}; }}
            QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {c['card']}; border: 2px solid {c['accent']}; width: 14px; height: 14px; margin: -5px 0; border-radius: 8px; }}
            """)
            self.nav_brand_lbl.setStyleSheet(f"font-size: 10.5pt; font-weight: 700; color: {c['ink']};")
            self.page_heading.setStyleSheet(f"font-size: 13.5pt; font-weight: 700; color: {c['ink']};")
            self.page_subtitle.setStyleSheet(f"font-size: 8.5pt; font-weight: 600; color: {c['caption']};")

        if hasattr(self, "menu_btn"):
            self.menu_btn.set_warmth(1.0 if is_warm_accent(self.accent_hex) else 0.0)

        self.fast_repaint_all()
        if self.isVisible(): self._sync_windows_backdrop()
        if self.current_key: self.refresh_origin_links()

    def _focus_search_box(self):
        if self.stack.currentIndex() != 0:
            self.switch_page(0)
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def _refresh_id_badge(self, own_id: str = ""):
        if own_id:
            self.id_badge.setText(f"新工坊 ID  {own_id}")
            self.id_badge.setCursor(Qt.CursorShape.PointingHandCursor)
            self.id_badge.setToolTip("左键在浏览器打开 Steam 工坊页面 · 右键复制 ID")
        else:
            self.id_badge.setText("PRIVATE · 新建项目")
            self.id_badge.setCursor(Qt.CursorShape.ArrowCursor)
            self.id_badge.setToolTip("")

    def _on_id_badge_clicked(self, event):
        if not self.current_key or self.current_key not in self.entries:
            return
        oid = self.entries[self.current_key].own_id
        if not oid:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl(WORKSHOP_URL.format(oid)))
        elif event.button() == Qt.MouseButton.RightButton:
            QApplication.clipboard().setText(oid)
            self.live_log_lbl.set_full_text(f"✓ 已复制新工坊 ID：{oid}")

    def restore_splitters(self):
        if g := self.settings.value("layout/geometry"):
            self.restoreGeometry(g)
            if (scr := self.screen()) is not None and not scr.availableGeometry().intersects(self.frameGeometry()):
                self.resize(1240, 820)
        if self.settings.value("layout/maximized", False, type=bool):
            self.showMaximized()
        if h := self.settings.value("layout/horizontal_splitter"): self.columns_splitter.restoreState(h)
        sizes = self.columns_splitter.sizes()
        if len(sizes) == 2 and sum(sizes) >= 685:
            first = max(250, min(sum(sizes) - 425, sizes[0]))
            if first != sizes[0]: self.columns_splitter.setSizes([first, sum(sizes) - first])

    def path_field(self, label: str, editor: QLineEdit, callback, extra_button=None):
        lay = QHBoxLayout(); lay.setSpacing(10)
        t = QLabel(label); t.setObjectName("pathLabel"); t.setFixedWidth(196); editor.setMinimumHeight(36)
        b = SmoothButton("更改路径"); b.setFixedWidth(98); b.clicked.connect(callback)
        lay.addWidget(t); lay.addWidget(editor, 1); lay.addWidget(b)
        if extra_button is not None: lay.addWidget(extra_button)
        return lay

    def workspace(self) -> Path: return Path(self.workspace_edit.text().strip()).expanduser().resolve()

    def persist_settings(self):
        self.settings.setValue("uploader", self.uploader_edit.text().strip())
        self.settings.setValue("workspace", self.workspace_edit.text().strip())

    def on_workspace_changed(self):
        self.persist_settings()
        if self.entries:
            self.log_line("归档目录已更改，已重新加载现有项目及注释。")
            paths = [item.source for item in self.entries.values()]
            self.entries.clear(); self.current_key = None
            for folder in paths:
                try: item = load_entry(folder, self.workspace()); self.entries[str(item.source)] = item
                except Exception as exc: self.log_line(f"无法重新加载 {folder}: {exc}")
            self.rebuild_rows()

    def browse_uploader(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 Darkest Dungeon 上传工具", self.uploader_edit.text(), "Executable (*.exe);;All Files (*)")
        if path: self.uploader_edit.setText(path); self.persist_settings()

    def auto_detect_uploader(self):
        found = detect_workshop_uploader()
        if found is not None:
            self.uploader_edit.setText(str(found))
            self.persist_settings()
            self.log_line(f"✓ 已自动探测到 Steam 工坊上传器：{found}")
            StudioDialog.information(self, "探测成功", f"已自动定位到暗黑地牢工坊上传器：\n{found}")
        else:
            StudioDialog.information(
                self, "未找到上传器",
                "未能在 Steam 注册表或各 Steam 库目录中找到 steam_workshop_upload.exe。\n请确认已安装 Darkest Dungeon，或点击「更改路径」手动选择。",
                severity="error",
            )

    def browse_workspace(self):
        path = QFileDialog.getExistingDirectory(self, "选择归档工作空间", self.workspace_edit.text())
        if path: self.workspace_edit.setText(path); self.on_workspace_changed()

    def _open_current_project_dir(self):
        if not self.current_key or self.current_key not in self.entries:
            StudioDialog.information(self, "未选中 MOD", "请先在工作台左侧列表选择一个 MOD。"); return
        folder = project_dir(self.workspace(), self.entries[self.current_key].source)
        if not folder.exists(): StudioDialog.information(self, "尚未归档", f"该 MOD 尚未生成归档目录：\n{folder}"); return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _copy_logs(self):
        if text := self.log_view.toPlainText().strip():
            QApplication.clipboard().setText(text)
            self.live_log_lbl.set_full_text("✓ 已将完整活动日志复制到剪贴板")

    def confirm_cleanup_cache(self):
        if self._pipeline_busy or (self.worker and self.worker.isRunning()) or (self.cache_worker and self.cache_worker.isRunning()): return
        self.save_current_draft()
        if not StudioDialog.ask(self, "清理已上传缓存", "仅回收工作空间中已确认上传成功的 MOD 副本（payload），保留所有 XML、ID、注释与日志。", confirm_text="清理缓存"): return
        self.set_busy(True); self.stop_btn.setEnabled(False); self.status_text.setText("CLEANING")
        self.cache_worker = CacheCleanupWorker(self.workspace())
        self.cache_worker.line.connect(self.log_line); self.cache_worker.completed.connect(self.on_cleanup_complete)
        self.cache_worker.finished.connect(self.on_cleanup_worker_finished); self.cache_worker.start()

    def on_cleanup_complete(self, projects: int, size: int, skipped: int, errors: int):
        msg = f"清理完成：回收 {projects} 个项目，释放 {human_bytes(size)}；跳过 {skipped} 个，错误 {errors} 个。"
        self.log_line(msg); self.status_text.setText("CHECK LOG" if errors else "READY")
        StudioDialog.information(self, "缓存清理完成", msg, severity="error" if errors else "info")

    def on_cleanup_worker_finished(self): self.cache_worker = None; self.set_busy(False)

    def scan_folder(self):
        start_dir = str(self.settings.value("paths/last_scan_dir", str(Path.home() / "Desktop")))
        if not Path(start_dir).is_dir(): start_dir = str(Path.home() / "Desktop")
        root = QFileDialog.getExistingDirectory(self, "选择包含 MOD 的文件夹", start_dir)
        if not root: return
        self.settings.setValue("paths/last_scan_dir", root)
        groups = discover_mod_groups(Path(root))
        folders = [m for g in groups for m in g.mods]
        if not folders: StudioDialog.information(self, "没有发现 MOD", "未找到有效 MOD 子目录。"); return
        self.add_candidates(folders, replace_existing=True, groups=groups)

    def add_single(self):
        start_dir = str(self.settings.value("paths/last_add_dir", str(Path.home() / "Desktop")))
        if not Path(start_dir).is_dir(): start_dir = str(Path.home() / "Desktop")
        path = QFileDialog.getExistingDirectory(self, "选择单个 MOD 目录", start_dir)
        if not path: return
        self.settings.setValue("paths/last_add_dir", str(Path(path).parent))
        chosen = Path(path); leaves = [m for g in discover_mod_groups(chosen) for m in g.mods]
        if len(leaves) > 1:
            StudioDialog.information(self, "请选择单个 MOD", f"此目录包含 {len(leaves)} 个独立 MOD，请使用「扫描 MOD 目录」。"); return
        if len(leaves) == 1 and leaves[0] != chosen.resolve(): chosen = leaves[0]
        self.add_candidates([chosen], replace_existing=False)

    def add_candidates(self, folders: list[Path], *, replace_existing: bool = False, groups: list[LibraryGroup] | None = None):
        if self._pipeline_busy or (self.worker and self.worker.isRunning()): return
        self.save_current_draft()
        loaded: dict[str, ModEntry] = {}
        errors = dup_path = dup_content = dup_id = 0
        base = {} if replace_existing else self.entries
        seen_paths = {str(e.source.resolve()).casefold() for e in base.values()}
        seen_fp = {e.content_fingerprint: e.source.name for e in base.values() if e.content_fingerprint}
        seen_own = {e.own_id: e.source.name for e in base.values() if e.own_id}
        seen_origin = {
            next(iter(e.original_ids)): e.source.name
            for e in base.values() if len(e.original_ids) == 1
        }
        for f in folders:
            try:
                norm_path = str(f.expanduser().resolve()).casefold()
                if norm_path in seen_paths:
                    dup_path += 1
                    continue
                item = load_entry(f, self.workspace())
                if item.content_fingerprint and item.content_fingerprint in seen_fp:
                    dup_content += 1
                    self.log_line(f"  ↺ 智能去重跳过「{item.source.name}」（与「{seen_fp[item.content_fingerprint]}」文件内容完全一致）")
                    continue
                if item.own_id and item.own_id in seen_own:
                    dup_id += 1
                    self.log_line(f"  ↺ 智能去重跳过「{item.source.name}」（与「{seen_own[item.own_id]}」绑定相同工坊 ID {item.own_id}）")
                    continue
                key = str(item.source)
                loaded[key] = item
                seen_paths.add(norm_path)
                if item.content_fingerprint:
                    seen_fp[item.content_fingerprint] = item.source.name
                if item.own_id:
                    seen_own[item.own_id] = item.source.name
                if len(item.original_ids) == 1:
                    oid = next(iter(item.original_ids))
                    if oid in seen_origin:
                        self.log_line(f"  ⚠ 来源 ID 重复提醒：「{item.source.name}」与「{seen_origin[oid]}」均来自原工坊 {oid}（若为不同变体或新旧版请留意）")
                    else:
                        seen_origin[oid] = item.source.name
            except Exception as exc:
                errors += 1; self.log_line(f"扫描失败 {f}: {exc}")
        total_dup = dup_path + dup_content + dup_id
        if not loaded:
            if total_dup:
                self.log_line(f"未新增 MOD：已智能去重跳过 {total_dup} 个重复项。")
            return
        if total_dup:
            self.log_line(f"智能去重：已自动跳过 {total_dup} 个重复项（同路径 {dup_path} / 同内容 {dup_content} / 同 ID {dup_id}）。")
        prev = len(self.entries)
        if replace_existing:
            self.entries = loaded; self.multi_keys.clear(); self.selection_anchor = self.current_key = None
            self._folder_groups = list(groups or [])
            self._folder_expanded.clear()
            self.log_line(f"扫描完成：已替换上次的 {prev} 项，识别 {len(loaded)} 个独立 MOD。" + (f"（{errors} 个失败）" if errors else ""))
        else:
            added = sum(k not in self.entries for k in loaded); self.entries.update(loaded)
            self._folder_groups.extend(groups or [])
            if len(loaded) == 1:
                self.current_key = next(iter(loaded))
            self.log_line(f"添加完成：新加入 {added} 个 MOD，当前共 {len(self.entries)} 个。")
        self.rebuild_rows()

    def _make_mod_row(self, key: str, layout: QVBoxLayout):
        row = ModRow(self.entries[key]); row.selected_row.connect(self.on_row_activated); row.selected_checked.connect(self.on_checked)
        row.context_requested.connect(self.on_row_context_menu)
        layout.addWidget(row); row.set_active(key in self.multi_keys); self.rows[key] = row

    def _subtree_keys(self, gk: str) -> list[str]:
        keys = list(self.collection_members.get(gk, []))
        for ck in self.collection_children.get(gk, []): keys.extend(self._subtree_keys(ck))
        return keys

    def _set_items_checked(self, keys, checked: bool) -> int:
        changed = 0
        for key in dict.fromkeys(keys):
            if (item := self.entries.get(key)) is None: continue
            if item.selected != checked: item.selected = checked; save_draft(self.workspace(), item); changed += 1
            if (row := self.rows.get(key)) is not None: row.update_content(item)
        self.refresh_count(); return changed

    def on_collection_checked(self, gk: str, checked: bool):
        if not self._pipeline_busy:
            keys = self._subtree_keys(gk); cnt = self._set_items_checked(keys, checked)
            self.log_line(f"已{'勾选' if checked else '排除'}文件夹 {self.collection_titles.get(gk, Path(gk).name)}：变更 {cnt} 项。")

    def on_collection_activated(self, gk: str, modifiers: int):
        if not (keys := set(self._subtree_keys(gk))): return
        if modifiers & int(Qt.KeyboardModifier.ControlModifier.value):
            self.multi_keys.difference_update(keys) if keys.issubset(self.multi_keys) else self.multi_keys.update(keys)
        else: self.multi_keys = keys
        self.selection_anchor = None; self._update_library_highlights(); self.refresh_count()

    def _update_library_highlights(self):
        for k, r in self.rows.items(): r.set_active(k in self.multi_keys)
        for gk, h in self.collection_headers.items():
            ks = self._subtree_keys(gk); h.set_highlighted(bool(ks) and set(ks).issubset(self.multi_keys))

    def _make_collection(self, gk: str, layout: QVBoxLayout):
        keys = self._subtree_keys(gk); exp = self.collection_expanded.get(gk, False)
        h = ModCollectionHeader(gk, self.collection_titles.get(gk, Path(gk).name), len(keys), exp)
        h.expanded_changed.connect(self.set_collection_expanded); h.highlighted.connect(self.on_collection_activated)
        h.checked_changed.connect(self.on_collection_checked); h.check.setEnabled(not self._pipeline_busy)
        layout.addWidget(h); self.collection_headers[gk] = h
        body = QWidget(); body.setObjectName("modCollectionChildren"); body.setMinimumWidth(0)
        inner = QVBoxLayout(body); inner.setContentsMargins(10, 4, 0, 5); inner.setSpacing(6); layout.addWidget(body)
        self.collection_bodies[gk], self.collection_layouts[gk] = body, inner
        if exp: self._populate_collection(gk)
        body.setVisible(exp)

    def _populate_collection(self, gk: str):
        if gk in self.collection_populated: return
        lay = self.collection_layouts[gk]
        if self.library_view_mode == "tag_group":
            for k in self.collection_members[gk]:
                if k in self.entries:
                    self._make_mod_row(k, lay)
        else:
            items = [(Path(k).name.casefold(), "mod", k) for k in self.collection_members[gk] if k in self.entries]
            items.extend((Path(k).name.casefold(), "group", k) for k in self.collection_children.get(gk, []))
            for _, kind, k in sorted(items):
                self._make_mod_row(k, lay) if kind == "mod" else self._make_collection(k, lay)
        self.collection_populated.add(gk)

    def set_collection_expanded(self, gk: str, expanded: bool):
        if gk not in self.collection_bodies or self.collection_expanded.get(gk) == bool(expanded): return
        self.collection_expanded[gk] = bool(expanded)
        if not self.search_query:
            if self.library_view_mode == "tag_group":
                self._tag_expanded[gk] = bool(expanded)
            elif self.library_view_mode == "folder":
                self._folder_expanded[gk] = bool(expanded)
        if expanded: self._populate_collection(gk)
        self.collection_bodies[gk].setVisible(bool(expanded)); self.collection_headers[gk].set_expanded(bool(expanded))
        self.list_layout.activate(); self.list_container.updateGeometry()

    def _key_visible_in_library(self, key: str) -> bool:
        for gk, members in self.collection_members.items():
            if key in members:
                anc = gk
                while anc:
                    if not self.collection_expanded.get(anc, False): return False
                    anc = self.collection_parents.get(anc)
                return True
        return True

    @staticmethod
    def _extract_collection_num(entry: ModEntry) -> tuple[int, str] | None:
        for raw in (entry.title or "", entry.source.name):
            cleaned = re.sub(r"[\r\n\t]+", " ", raw).strip()
            m = re.match(r"^(\d+)(.*)$", cleaned, re.DOTALL)
            if m:
                num = int(m.group(1))
                if 0 <= num <= 1000:
                    mod_name = m.group(2).lstrip(" _.-:：、+\t").casefold()
                    return num, mod_name
        return None

    @classmethod
    def _collection_order_key(cls, entry: ModEntry):
        title = re.sub(r"[\r\n\t]+", " ", entry.title or "").strip()
        src = entry.source.name.strip()
        extracted = cls._extract_collection_num(entry)
        if extracted is not None:
            num, mod_name = extracted
            return (0, num, mod_name, title.casefold(), src.casefold())
        return (1, 0, (title or src).casefold(), title.casefold(), src.casefold())

    @classmethod
    def _tag_sort_key(cls, entry: ModEntry):
        rank_map = {t: idx for idx, t in enumerate(WORKSHOP_TAGS)}
        ck = cls._collection_order_key(entry)
        if not entry.tags:
            return (len(WORKSHOP_TAGS), ck)
        first_rank = min(rank_map.get(t, len(WORKSHOP_TAGS)) for t in entry.tags)
        return (first_rank, ck)

    def _matches_search(self, item: ModEntry) -> bool:
        q = self.search_query.strip().casefold()
        if not q:
            return True
        hay = " ".join((
            re.sub(r"[\r\n\t]+", " ", item.title),
            item.source.name,
            item.own_id,
            " ".join(item.original_ids),
            " ".join(item.tags),
        )).casefold()
        return all(tok in hay for tok in q.split())

    def _apply_search_filter(self):
        new_q = self.search_edit.text().strip()
        if new_q != self.search_query:
            self.search_query = new_q
            self.rebuild_rows()

    def _ordered_entry_keys(self, *, filtered: bool = False) -> list[str]:
        if self.library_view_mode == "collection":
            keys = sorted(self.entries.keys(), key=lambda k: self._collection_order_key(self.entries[k]))
        elif self.library_view_mode in ("tag_sort", "tag_group"):
            keys = sorted(self.entries.keys(), key=lambda k: self._tag_sort_key(self.entries[k]))
        else:
            keys = list(self.entries.keys())
        if filtered and self.search_query:
            return [k for k in keys if self._matches_search(self.entries[k])]
        return keys

    def _displayed_mod_keys(self) -> list[str]:
        filtered_keys = self._ordered_entry_keys(filtered=True)
        if self.library_view_mode in ("collection", "tag_sort"):
            return filtered_keys
        allowed = set(filtered_keys)
        ordered: list[str] = []
        def _walk_group(gk: str):
            if not self.collection_expanded.get(gk, False):
                return
            items = [(Path(k).name.casefold(), "mod", k) for k in self.collection_members.get(gk, []) if k in allowed]
            items.extend((Path(k).name.casefold(), "group", k) for k in self.collection_children.get(gk, []))
            for _, kind, k in sorted(items):
                if kind == "mod":
                    ordered.append(k)
                else:
                    _walk_group(k)
        if self.library_view_mode == "tag_group":
            for gk in self.collection_members:
                _walk_group(gk)
            return ordered
        grouped = {k for ks in self.collection_members.values() for k in ks if k in allowed}
        for gk in self.collection_members:
            if (p := self.collection_parents.get(gk)) is None or p not in self.collection_members:
                _walk_group(gk)
        for k in filtered_keys:
            if k not in grouped:
                ordered.append(k)
        return ordered

    def on_library_view_mode_changed(self, mode: str):
        if mode in ("folder", "collection", "tag_sort", "tag_group") and mode != self.library_view_mode:
            self.library_view_mode = mode
            self.settings.setValue("layout/library_view_mode", mode)
            self.rebuild_rows()

    @staticmethod
    def _format_num_ranges(nums: list[int]) -> str:
        if not nums:
            return ""
        ranges: list[str] = []
        s = e = nums[0]
        for n in nums[1:]:
            if n == e + 1:
                e = n
            else:
                ranges.append(f"{s}" if s == e else f"{s}–{e}")
                s = e = n
        ranges.append(f"{s}" if s == e else f"{s}–{e}")
        return ", ".join(ranges)

    def sort_and_audit_numbers(self):
        if not self.entries:
            return
        self.save_current_draft()
        for item in self.entries.values():
            cleaned = re.sub(r"[\r\n\t]+", " ", item.title).strip()
            if cleaned and cleaned != item.title:
                item.title = cleaned
        if self.library_view_mode == "folder":
            self.library_view_mode = "collection"
            self.library_mode_selector.set_value("collection", emit=False)
            self.settings.setValue("layout/library_view_mode", "collection")
        self.rebuild_rows()

        by_num: dict[int, list[str]] = {}
        unnumbered: list[str] = []
        for k in self._ordered_entry_keys():
            item = self.entries[k]
            label = re.sub(r"[\r\n\t]+", " ", item.title).strip() or item.source.name
            ext = self._extract_collection_num(item)
            if ext is None:
                unnumbered.append(label)
            else:
                by_num.setdefault(ext[0], []).append(label)

        dups = {n: names for n, names in sorted(by_num.items()) if len(names) > 1}
        max_n = max(by_num) if by_num else 0
        missing = [n for n in range(1, max_n + 1) if n not in by_num] if max_n else []

        lines = [f"已重排 {len(self.entries)} 个 MOD（已编号 {sum(len(v) for v in by_num.values())} 个，最大序号 {max_n}）。"]
        if dups:
            lines.append(f"\n⚠ 发现 {len(dups)} 组重复序号：")
            for n, names in list(dups.items())[:10]:
                lines.append(f"  • 序号 {n} ({len(names)}项)：" + " / ".join(names))
            if len(dups) > 10:
                lines.append(f"  …其余 {len(dups) - 10} 组请见运行日志")
        else:
            lines.append("\n✓ 无重复序号。")

        if missing:
            lines.append(f"\n⚠ 1–{max_n} 共缺失 {len(missing)} 个序号：{self._format_num_ranges(missing)}")
        elif max_n:
            lines.append(f"\n✓ 1–{max_n} 序号连续无漏号。")

        if unnumbered:
            lines.append(f"\n⚠ 未识别到 1–1000 序号 ({len(unnumbered)}项)：")
            for nm in unnumbered[:8]:
                lines.append(f"  • {nm}")
            if len(unnumbered) > 8:
                lines.append(f"  …等共 {len(unnumbered)} 项")

        self.log_line("\n[ 序号排序与核验 ] " + lines[0])
        for n, names in dups.items():
            self.log_line(f"  ⚠ 重号 {n}：" + " / ".join(names))
        if missing:
            self.log_line(f"  ⚠ 漏号 (1–{max_n})：{self._format_num_ranges(missing)}")
        if unnumbered:
            self.log_line(f"  ⚠ 未编号 ({len(unnumbered)})：" + ", ".join(unnumbered[:15]) + ("…" if len(unnumbered) > 15 else ""))
        if StudioDialog.ask(
            self, "序号排序与核验报告", "\n".join(lines),
            confirm_text="拖拽重排序号", cancel_text="关闭",
        ):
            rows_data = []
            for k in self._ordered_entry_keys():
                item = self.entries[k]
                clean_title = re.sub(r"[\r\n\t]+", " ", item.title).strip() or item.source.name
                ext = self._extract_collection_num(item)
                orig_num = ext[0] if ext is not None else None
                base_title = strip_title_index(clean_title) if orig_num is not None else clean_title
                rows_data.append((k, orig_num, base_title, clean_title))
            dlg = CollectionReorderDialog(self, rows_data, default_mode="bump")
            if dlg.exec() == QDialog.DialogCode.Accepted and (updates := dlg.result_updates()):
                for k, new_title in updates.items():
                    if k in self.entries:
                        self.entries[k].title = new_title
                        save_draft(self.workspace(), self.entries[k])
                if self.current_key in updates:
                    self.editor_loading = True
                    self.title_edit.setText(updates[self.current_key])
                    self.editor_loading = False
                    self.preview_description()
                self.rebuild_rows()
                self.log_line(f"✓ 拖拽重排完成：已更新 {len(updates)} 个 MOD 的合集序号。")

    def _apply_library_view_grouping(self):
        for d in (self.collection_members, self.collection_parents, self.collection_children, self.collection_expanded, self.collection_titles):
            d.clear()
        if self.library_view_mode in ("collection", "tag_sort"):
            return
        filtering = bool(self.search_query)
        visible_keys = self._ordered_entry_keys(filtered=True)
        visible_set = set(visible_keys)
        if self.library_view_mode == "tag_group":
            buckets: dict[str, list[str]] = {}
            for k in visible_keys:
                item = self.entries[k]
                tag = item.tags[0] if item.tags else ""
                gk = f"tag:{tag or '__none__'}"
                buckets.setdefault(gk, []).append(k)
                self.collection_titles[gk] = tag or "未设标签"
            for gk, keys in buckets.items():
                self.collection_members[gk] = keys
                self.collection_parents[gk] = None
                if filtering:
                    self.collection_expanded[gk] = True
                else:
                    if gk not in self._tag_expanded:
                        self._tag_expanded[gk] = (len(keys) <= 10) or (self.current_key in keys) or (len(self.entries) <= 20)
                    self.collection_expanded[gk] = self._tag_expanded[gk]
            return
        for g in self._folder_groups:
            keys = [str(m.resolve()) for m in g.mods if str(m.resolve()) in visible_set]
            if not keys or (len(keys) == 1 and keys[0] == str(g.folder.resolve())):
                continue
            gk = str(g.folder.resolve())
            pk = str(g.parent.resolve()) if g.parent else None
            existing = self.collection_members.setdefault(gk, [])
            for k in keys:
                if k not in existing:
                    existing.append(k)
            self.collection_parents[gk] = pk
            self.collection_titles[gk] = g.folder.name
            if filtering:
                self.collection_expanded[gk] = True
            else:
                if gk not in self._folder_expanded:
                    self._folder_expanded[gk] = (pk is None and len(existing) <= 10)
                self.collection_expanded[gk] = self._folder_expanded[gk]
        for gk, pk in list(self.collection_parents.items()):
            if pk and pk in self.collection_members:
                children = self.collection_children.setdefault(pk, [])
                if gk not in children:
                    children.append(gk)
            elif pk:
                self.collection_parents[gk] = None

    def _extract_dropped_dirs(self, event) -> list[Path]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile() and Path(u.toLocalFile()).is_dir()]

    def dragEnterEvent(self, event):
        if self._pipeline_busy or (self.worker and self.worker.isRunning()):
            event.ignore(); return
        event.acceptProposedAction() if self._extract_dropped_dirs(event) else event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        if self._pipeline_busy or (self.worker and self.worker.isRunning()):
            event.ignore(); return
        dirs = self._extract_dropped_dirs(event)
        if not dirs:
            event.ignore(); return
        event.acceptProposedAction()
        all_groups: list[LibraryGroup] = []
        all_mods: list[Path] = []
        seen: set[Path] = set()
        for d in dirs:
            for g in discover_mod_groups(d):
                leaves = tuple(m for m in g.mods if m not in seen)
                if leaves:
                    seen.update(leaves)
                    all_mods.extend(leaves)
                    all_groups.append(LibraryGroup(g.folder, leaves, g.parent))
        if not all_mods:
            self.log_line("拖入的文件夹中未发现有效 MOD。")
            return
        self.add_candidates(all_mods, replace_existing=False, groups=all_groups)
        if self.stack.currentIndex() != 0:
            self.switch_page(0)

    def rebuild_rows(self):
        self.multi_keys.intersection_update(self.entries)
        if self.selection_anchor not in self.entries: self.selection_anchor = None
        self.list_container.setUpdatesEnabled(False)
        try:
            self._rebuild_rows_inner()
        finally:
            self.list_container.setUpdatesEnabled(True)

    def _rebuild_rows_inner(self):
        while self.list_layout.count():
            if (it := self.list_layout.takeAt(0)).widget(): it.widget().deleteLater()
        for d in (self.rows, self.collection_headers, self.collection_bodies, self.collection_layouts): d.clear()
        self.collection_populated.clear()
        self._apply_library_view_grouping()
        visible_keys = self._ordered_entry_keys(filtered=True)
        visible_set = set(visible_keys)
        grouped = {k for ks in self.collection_members.values() for k in ks if k in visible_set}
        for gk in self.collection_members:
            if (p := self.collection_parents.get(gk)) is None or p not in self.collection_members:
                self._make_collection(gk, self.list_layout)
        for k in visible_keys:
            if k not in grouped: self._make_mod_row(k, self.list_layout)
        self.list_layout.addStretch(1)

        if self.current_key not in self.entries or (self.current_key and not self._key_visible_in_library(self.current_key)):
            self.current_key = next((k for k in self._ordered_entry_keys(filtered=True) if self._key_visible_in_library(k)), None)
        if self.current_key:
            if not self.multi_keys: self.multi_keys.add(self.current_key)
            self.show_item(self.current_key)
        else:
            self.enable_editor(False); self.id_badge.setText("等待选择 MOD"); self.id_badge.setCursor(Qt.CursorShape.ArrowCursor); self.id_badge.setToolTip(""); self.preview_meta.setText("PRIVATE · 等待选择")
            self.origin_label.setText("展开文件夹并选择一个 MOD"); self.editor_loading = True
            self.title_edit.clear(); self.note_edit.clear(); self.description.clear(); self.upload_title_hint.set_full_text("")
            for cb in self.tag_checks.values(): cb.setChecked(False)
            self.tags_counter.setText("未选标签"); self.editor_loading = False
            self.clear_preview_image()
        self.refresh_count()

    def refresh_count(self):
        total, marked = len(self.entries), sum(i.selected for i in self.entries.values())
        self.count_label.setText(f"{total} 项 · 待传 {marked}")
        shown = len(self._ordered_entry_keys(filtered=True)) if self.search_query else total
        self.list_hint.setText(f"{shown}/{total} 项" if self.search_query else f"{total} 项")
        en = bool(self.multi_keys) and not self._pipeline_busy
        self.check_selected_button.setEnabled(en); self.uncheck_selected_button.setEnabled(en)
        self.clear_library_button.setEnabled(total > 0 and not self._pipeline_busy)
        self.nav_sort_audit.setEnabled(total > 0 and not self._pipeline_busy)
        self.upload_btn.label_text = f"归档上传 {marked}"; self.upload_btn.update()
        for gk, h in self.collection_headers.items():
            ks = self._subtree_keys(gk)
            h.update_summary(len(ks), sum(1 for k in ks if k in self.entries and self.entries[k].selected))
            h.set_highlighted(bool(ks) and set(ks).issubset(self.multi_keys))
        self.pick_all.blockSignals(True)
        self.pick_all.setCheckState(Qt.CheckState.Unchecked if (total == 0 or marked == 0) else (Qt.CheckState.Checked if marked == total else Qt.CheckState.PartiallyChecked))
        self.pick_all.blockSignals(False)

    def on_checked(self, key: str, checked: bool):
        item = self.entries[key]; item.selected = checked; save_draft(self.workspace(), item)
        if key in self.rows: self.rows[key].update_content(item); self.rows[key].flash()
        self.refresh_count()

    def set_highlighted_checked(self, checked: bool):
        if self.multi_keys and not self._pipeline_busy:
            cnt = self._set_items_checked(self.multi_keys, checked)
            self.log_line(f"已{'勾选' if checked else '排除'}高亮的 {len(self.multi_keys)} 个 MOD，变更 {cnt} 项。")

    def on_row_activated(self, key: str, modifiers: int):
        if key not in self.entries: return
        keys = self._displayed_mod_keys()
        if key not in keys: keys = self._ordered_entry_keys()
        shift, ctrl = bool(modifiers & int(Qt.KeyboardModifier.ShiftModifier.value)), bool(modifiers & int(Qt.KeyboardModifier.ControlModifier.value))
        if shift and self.selection_anchor in self.entries:
            s, e = keys.index(self.selection_anchor), keys.index(key)
            grp = set(keys[min(s, e):max(s, e) + 1])
            self.multi_keys = self.multi_keys | grp if ctrl else grp
        elif ctrl:
            self.multi_keys.discard(key) if key in self.multi_keys else self.multi_keys.add(key); self.selection_anchor = key
        else:
            self.multi_keys = {key}; self.selection_anchor = key
        self.show_item(key); self._update_library_highlights(); self.refresh_count()

    def toggle_all(self, state: int):
        if not self._pipeline_busy: self._set_items_checked(self.entries, state == Qt.CheckState.Checked.value)

    def _remove_entries(self, keys: list[str]):
        if self._pipeline_busy or (self.worker and self.worker.isRunning()):
            return
        removed = 0
        for k in keys:
            if k in self.entries:
                del self.entries[k]
                self.multi_keys.discard(k)
                if self.current_key == k:
                    self.current_key = None
                removed += 1
        if removed:
            self.rebuild_rows()
            self.log_line(f"已从当前列表移除 {removed} 个 MOD（原始文件与草稿均保留）。")

    def on_row_context_menu(self, key: str, global_pos):
        if key not in self.entries:
            return
        if key not in self.multi_keys:
            self.on_row_activated(key, 0)
        item = self.entries[key]
        menu = StudioMenu(self)
        busy = self._pipeline_busy or bool(self.worker and self.worker.isRunning())
        act_toggle = QAction("取消勾选此 MOD" if item.selected else "勾选此 MOD", menu)
        act_toggle.setEnabled(not busy)
        act_toggle.triggered.connect(lambda: self.on_checked(key, not item.selected))
        menu.addAction(act_toggle)

        act_src = QAction("打开源 MOD 文件夹", menu)
        act_src.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(item.source))))
        menu.addAction(act_src)

        proj = project_dir(self.workspace(), item.source)
        act_proj = QAction("打开归档项目文件夹", menu)
        act_proj.setEnabled(proj.exists())
        act_proj.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(proj))))
        menu.addAction(act_proj)

        menu.addSeparator()
        act_own = QAction(f"在 Steam 打开新工坊 ({item.own_id})" if item.own_id else "在 Steam 打开新工坊（尚未上传）", menu)
        act_own.setEnabled(bool(item.own_id))
        if item.own_id:
            act_own.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(WORKSHOP_URL.format(item.own_id))))
        menu.addAction(act_own)

        if len(item.original_ids) == 1:
            oid = next(iter(item.original_ids))
            act_ori = QAction(f"打开原工坊页面 ({oid})", menu)
            act_ori.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(WORKSHOP_URL.format(oid))))
            menu.addAction(act_ori)

        act_cpt = QAction("复制上传标题", menu)
        act_cpt.triggered.connect(lambda: QApplication.clipboard().setText(upload_title_for(item, strip_numbers=self.strip_numbers, strip_v2=self.strip_v2)))
        menu.addAction(act_cpt)

        if item.own_id:
            act_cpi = QAction("复制新工坊 ID", menu)
            act_cpi.triggered.connect(lambda: QApplication.clipboard().setText(item.own_id))
            menu.addAction(act_cpi)

        menu.addSeparator()
        act_only_un = QAction("仅勾选未上传 MOD", menu)
        act_only_un.setEnabled(not busy)
        act_only_un.triggered.connect(self._select_only_unuploaded)
        menu.addAction(act_only_un)
        act_ex_done = QAction("排除已上传 MOD", menu)
        act_ex_done.setEnabled(not busy)
        act_ex_done.triggered.connect(self._exclude_uploaded)
        menu.addAction(act_ex_done)
        menu.addSeparator()
        targets = list(self.multi_keys) if len(self.multi_keys) > 1 and key in self.multi_keys else [key]
        act_rm = QAction(f"从列表移除 ({len(targets)} 项)" if len(targets) > 1 else "从列表移除", menu)
        act_rm.setEnabled(not busy)
        act_rm.triggered.connect(lambda: self._remove_entries(targets))
        menu.addAction(act_rm)
        menu.exec(global_pos)

    def _select_only_unuploaded(self):
        if self._pipeline_busy: return
        un = [k for k, e in self.entries.items() if e.status != "SUCCESS"]
        dn = [k for k, e in self.entries.items() if e.status == "SUCCESS"]
        self._set_items_checked(un, True)
        self._set_items_checked(dn, False)
        self.log_line(f"已勾选 {len(un)} 个未上传 MOD，排除 {len(dn)} 个已上传项。")

    def _exclude_uploaded(self):
        if self._pipeline_busy: return
        dn = [k for k, e in self.entries.items() if e.status == "SUCCESS" and e.selected]
        cnt = self._set_items_checked(dn, False)
        self.log_line(f"已排除 {cnt} 个已上传 MOD。")

    def clear_library(self):
        if self._pipeline_busy or (self.worker and self.worker.isRunning()) or not self.entries: return
        cnt = len(self.entries); self.draft_timer.stop(); self.save_current_draft()
        self.entries.clear(); self.current_key = self.selection_anchor = None; self.multi_keys.clear()
        self._folder_groups.clear(); self._folder_expanded.clear(); self._tag_expanded.clear()
        for d in (self.collection_members, self.collection_parents, self.collection_children, self.collection_expanded, self.collection_titles): d.clear()
        self.rebuild_rows(); self.log_line(f"已清除当前 LIBRARY 的 {cnt} 个 MOD；原始文件、草稿、工坊 ID 与日志均保留。")

    def enable_editor(self, enabled: bool):
        self.title_edit.setEnabled(enabled); self.note_edit.setEnabled(enabled)
        for cb in getattr(self, "tag_checks", {}).values(): cb.setEnabled(enabled)

    def show_item(self, key: str):
        if key not in self.entries: return
        if key != self.current_key: self.save_current_draft()
        self.current_key = key; item = self.entries[key]; self._draft_dirty = False; self.editor_loading = True; self.enable_editor(True)
        self.title_edit.setText(item.title); self.note_edit.setPlainText(item.note)
        tag_set = set(item.tags)
        for tname, cb in self.tag_checks.items(): cb.setChecked(tname in tag_set)
        self.tags_counter.setText(f"已选 {len(tag_set)} 项" if tag_set else "未选标签")
        self._refresh_id_badge(item.own_id)
        self.refresh_origin_links(); self.reload_preview_image(); self.editor_loading = False
        self.preview_description(); self.editor_scroll.verticalScrollBar().setValue(0); self._update_library_highlights()
        self.editor_pulse.stop(); self.editor_card.set_selection_pulse(1.0)
        self.editor_pulse.setStartValue(1.0); self.editor_pulse.setEndValue(0.0); self.editor_pulse.start()

    def refresh_origin_links(self):
        if not self.current_key or self.current_key not in self.entries: return
        item = self.entries[self.current_key]
        if item.original_ids:
            c = current_colors()
            links = "".join(f'<a href="{escape(WORKSHOP_URL.format(oid))}" style="color:{c["accent"]};">{escape(WORKSHOP_URL.format(oid))}</a><br>' for oid in item.original_ids)
            self.origin_label.setText("<b>扫描到的原始工坊条目（未核实）：</b><br>" + links)
        else:
            self.origin_label.setText("未在原始 project.xml 中找到 Steam 工坊 ID；不自动添加来源说明。")

    def editor_changed(self):
        if not self.editor_loading and self.current_key:
            self._draft_dirty = True
            item = self.entries[self.current_key]
            item.title, item.note = self.title_edit.text(), self.note_edit.toPlainText()
            item.tags = [t for t in WORKSHOP_TAGS if self.tag_checks[t].isChecked()]
            self.tags_counter.setText(f"已选 {len(item.tags)} 项" if item.tags else "未选标签")
            if self.current_key in self.rows:
                self.rows[self.current_key].update_content(item)
            self.preview_description(); self.draft_timer.start()

    def clear_preview_image(self):
        self.icon_preview.clear(); self.icon_dimensions.setText("尚未选择 MOD"); self.icon_size_label.setText("文件大小：—")
        self.icon_status.setText("原图只读 · 不改变源文件"); self.icon_open_button.setEnabled(False); self.icon_reload_button.setEnabled(False)
        self._preview_problem = False; self._refresh_preview_status_color()

    def _refresh_preview_status_color(self):
        c = current_colors()
        self.icon_status.setStyleSheet(f"color: {c['danger_text'] if getattr(self, '_preview_problem', False) else c['muted']}; font-size: 9pt;")

    def reload_preview_image(self):
        if not self.current_key or self.current_key not in self.entries: self.clear_preview_image(); return
        item = self.entries[self.current_key]; path = item.source / "preview_icon.png"; size = 0
        try: size = path.stat().st_size
        except OSError: pass
        item.source_preview_bytes = size; dims, err = self.icon_preview.load_image(path)
        self.icon_dimensions.setText(f"{dims[0]} × {dims[1]} 像素" if dims else "图像不可用")
        self.icon_size_label.setText(f"文件大小：{size:,} 字节 ({size / 1024:.1f} KB)" if size else "文件大小：—")
        self.icon_open_button.setEnabled(path.is_file()); self.icon_reload_button.setEnabled(True)
        if err: self.icon_status.setText(f"预览失败：{err}"); self._preview_problem = True
        elif size >= 1_000_000: self.icon_status.setText("超过 Steam 1 MB 上限；归档时只压缩上传副本"); self._preview_problem = True
        elif size >= 900_000: self.icon_status.setText("达到 900 KB 压缩阈值；归档时将自动压缩副本"); self._preview_problem = True
        else: self.icon_status.setText("✓ 大小合规 · 原始文件不会被修改"); self._preview_problem = False
        self._refresh_preview_status_color(); self.preview_description()

    def open_preview_image(self):
        if self.current_key and (p := self.entries[self.current_key].source / "preview_icon.png").is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def on_strip_numbers_toggled(self, checked: bool):
        self.strip_numbers = bool(checked)
        self.settings.setValue("upload/strip_collection_numbers", self.strip_numbers)
        self.preview_description()

    def on_strip_v2_toggled(self, checked: bool):
        self.strip_v2 = bool(checked)
        self.settings.setValue("upload/strip_v2_suffix", self.strip_v2)
        self.preview_description()

    def preview_description(self):
        if not self.current_key: return
        item = self.entries[self.current_key]
        up_title = upload_title_for(item, strip_numbers=self.strip_numbers, strip_v2=self.strip_v2)
        if up_title != item.title.strip():
            self.upload_title_hint.set_full_text(f"→ 上传名：{up_title}")
        else:
            self.upload_title_hint.set_full_text("")
        self.description.setPlainText(description_for(item, strip_numbers=self.strip_numbers, strip_v2=self.strip_v2)); self.note_counter.setText(f"{len(item.note)} 字")
        self.preview_meta.setText("图片超限 · 归档时自动压缩" if item.source_preview_bytes >= 1_000_000 else (
            "缺少 preview_icon.png" if item.source_preview_bytes == 0 else f"预览图 {item.source_preview_bytes // 1024} KB · PRIVATE"
        ))

    def save_current_draft(self):
        if self._draft_dirty and self.current_key and self.current_key in self.entries:
            save_draft(self.workspace(), self.entries[self.current_key])
            self._draft_dirty = False

    def _refresh_live_log_color(self):
        if hasattr(self, "live_log_lbl"):
            c = current_colors()
            col = c.get(f"log_{getattr(self, '_live_log_role', 'text')}", c["caption"])
            self.live_log_lbl.setStyleSheet(f"color: {col}; font-size: 8.8pt; font-weight: 600;")

    def log_line(self, message: str):
        self.log_view.appendPlainText(message)
        bar = self.log_view.verticalScrollBar(); bar.setValue(bar.maximum())
        if (clean := message.strip()) and hasattr(self, "live_log_lbl"):
            self._live_log_role = classify_log_role(clean)
            self.live_log_lbl.set_full_text(clean)
            self._refresh_live_log_color()

    def animate_progress(self, value: int):
        self.progress_anim.stop(); self.progress_anim.setStartValue(self.progress.value()); self.progress_anim.setEndValue(value); self.progress_anim.start()

    def start_pipeline(self, upload: bool):
        if self._pipeline_busy or (self.worker and self.worker.isRunning()) or (self.cache_worker and self.cache_worker.isRunning()): return
        self.save_current_draft()
        if not (selected := [self.entries[k] for k in self._ordered_entry_keys() if self.entries[k].selected]):
            StudioDialog.information(self, "请选择 MOD", "请先扫描并勾选至少一个 MOD。"); return
        uploader = Path(self.uploader_edit.text().strip())
        if upload and not uploader.is_file():
            if (auto := detect_workshop_uploader()) is not None and StudioDialog.ask(
                self,
                "上传器路径无效 · 已自动探测",
                f"当前配置的上传器不存在：\n{uploader}\n\n已自动探测到可用路径：\n{auto}\n\n是否改用该路径并继续上传？",
                confirm_text="改用并上传",
            ):
                uploader = auto
                self.uploader_edit.setText(str(auto))
                self.persist_settings()
            else:
                StudioDialog.information(self, "上传器路径无效", f"找不到 exe：\n{uploader}", severity="error"); return
        if self.update_check.isChecked() and upload and not StudioDialog.ask(
            self, "确认允许更新 / 重试", "已开启「允许更新已有项目」，将使用现有工坊 ID 提交更新。请先确认旧项目存在且归属于你。"
        ): return
        self.persist_settings(); self._pipeline_started_at = time.monotonic(); self.progress.setValue(0); self.status_text.setText("UPLOADING" if upload else "PREPARING"); self.set_busy(True)
        self.log_line("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"); self.log_line(f"开始{'归档并上传' if upload else '仅准备归档'}：{len(selected)} 个 MOD")
        if upload: self.switch_page(1)
        self.worker = PipelineWorker(selected, self.workspace(), uploader, upload, self.update_check.isChecked(), self.strip_numbers, self.strip_v2)
        self.worker.line.connect(self.log_line); self.worker.changed.connect(self.on_item_status)
        self.worker.progress.connect(self.animate_progress); self.worker.completed.connect(self.on_pipeline_complete)
        self.worker.finished.connect(self.on_worker_finished); self.worker.start()

    def on_item_status(self, key: str, state: str, own_id: str):
        if key in self.entries:
            item = self.entries[key]; prev = item.status; item.status, item.own_id = state, own_id
            if key in self.rows:
                self.rows[key].update_content(item)
                if prev != state and state in ("SUCCESS", "UNCONFIRMED"): self.rows[key].flash()
            self.refresh_count()
            if self.current_key == key: self._refresh_id_badge(own_id)

    def on_pipeline_complete(self, completed: int, failures: int, cancelled: bool):
        self.set_busy(False); self.status_text.setText("CHECK LOG" if failures else ("STOPPED" if cancelled else "COMPLETE"))
        elapsed = max(0, round(time.monotonic() - self._pipeline_started_at))
        mins, secs = divmod(elapsed, 60)
        dur_txt = f"{mins}m {secs}s" if mins else f"{secs}s"
        self.log_line(f"本轮结束：完成 / 跳过 {completed} 个，失败 {failures} 个 · 耗时 {dur_txt}。")

    def on_worker_finished(self): self.worker = None

    def set_busy(self, busy: bool):
        for w in (self.prepare_btn, self.upload_btn, self.scan_button, self.add_button, self.cleanup_cache_button,
                  self.uploader_edit, self.workspace_edit, self.update_check, self.strip_num_check, self.strip_v2_check, self.pick_all):
            w.setEnabled(not busy)
        self.stop_btn.setEnabled(busy); self.enable_editor(not busy and bool(self.current_key))
        for w in (self.check_selected_button, self.uncheck_selected_button): w.setEnabled(not busy and bool(self.multi_keys))
        self.clear_library_button.setEnabled(not busy and bool(self.entries))
        self.nav_sort_audit.setEnabled(not busy and bool(self.entries))
        for h in self.collection_headers.values(): h.check.setEnabled(not busy)
        self._pipeline_busy = busy; self._update_ambient_timer()
        for r in self.rows.values(): r.box.setEnabled(not busy)

    def request_stop(self):
        if self.worker:
            self.worker.stop_requested = True; self.status_text.setText("STOPPING")
            self.log_line("已申请停止：当前正在执行的 MOD 会完成后停止后续任务。"); self.stop_btn.setEnabled(False)

    def _play_entrance(self):
        dur = motion_duration(260)
        if dur <= 0:
            self.setWindowOpacity(1.0)
            return
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(dur)
        anim.setEasingCurve(mac_curve())
        anim.setStartValue(self.windowOpacity())
        anim.setEndValue(1.0)
        anim.finished.connect(lambda: self.setWindowOpacity(1.0))
        self._entrance_anim = anim
        anim.start()

    def closeEvent(self, event):
        if self._close_ready:
            super().closeEvent(event)
            return
        if self._closing_anim_active:
            event.ignore()
            return
        if self.cache_worker and self.cache_worker.isRunning():
            StudioDialog.information(self, "正在清理缓存", "正在清理历史上传副本，请在完成后关闭窗口。"); event.ignore(); return
        if self.worker and self.worker.isRunning():
            self.request_stop(); StudioDialog.information(self, "正在上传", "请在当前提交结束后关闭窗口，已停止后续任务。"); event.ignore(); return
        self.save_current_draft(); self.persist_settings()
        self.settings.setValue("appearance/mode", self.appearance_mode)
        self.settings.setValue("appearance/material_mode", self.material_mode)
        self.settings.setValue("appearance/glass_strength", self.glass_strength)
        self.settings.setValue("appearance/backdrop_mode", self.backdrop_mode)
        self.settings.setValue("appearance/ambient_motion", self.ambient_motion_on)
        self.settings.setValue("appearance/drag_assist", self.drag_assist)
        self.settings.setValue("appearance/accent_hex", self.accent_hex)
        self.settings.setValue("layout/nav_collapsed", self.nav_collapsed)
        self.settings.setValue("layout/horizontal_splitter", self.columns_splitter.saveState())
        self.settings.setValue("layout/maximized", self.isMaximized())
        if not self.isMaximized():
            self.settings.setValue("layout/geometry", self.saveGeometry())

        if hasattr(self, "_ambient_timer"):
            self._ambient_timer.stop()
        if hasattr(self, "draft_timer"):
            self.draft_timer.stop()
        if self._entrance_anim is not None:
            self._entrance_anim.stop()

        dur = motion_duration(180)
        if dur > 0 and self.isVisible() and not self.isMinimized():
            event.ignore()
            self._closing_anim_active = True
            anim = QPropertyAnimation(self, b"windowOpacity", self)
            anim.setDuration(dur)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.setStartValue(self.windowOpacity())
            anim.setEndValue(0.0)
            def _finish_close():
                self._close_ready = True
                self.close()
            anim.finished.connect(_finish_close)
            self._exit_anim = anim
            anim.start()
            return
        self._close_ready = True
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DD Workshop Studio")
    app.setOrganizationName("DDWorkshopStudio")
    app.setApplicationVersion("2.3.0")
    app.setStyle("Fusion")
    app.setFont(studio_font(10.0))
    if (image := find_asset_file("app.ico") or find_brand_image("blue")) is not None:
        app.setWindowIcon(QIcon(str(image)))
    window = StudioWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()