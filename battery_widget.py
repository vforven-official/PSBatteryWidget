"""
battery_widget.py
Dynamic morphing desktop card widget for PlayStation accessories.
Features:
- Desktop Widget Enabled / Tray-Only Mode (persisted)
- Reliable Tray Toggle (User Hide / Show) without poll loop resurrecting it
- Dynamic Auto-Shrink / Expand (0 -> retract, 1 -> 38px, 2 -> 68px)
- Toast notifications for connect, disconnect, unplug (discharging), and charging
- Intelligent Connection Settling: Displays 'Checking...' and suppresses false low-battery alerts on fresh connect
- Light / Dark mode switching (persisted)
- Low battery alerts (<= 20%) via Windows System Tray notifications
- Magnetic 4-edge docking (Right, Left, Top, Bottom)
- Persistent position, theme, and auto-hide settings in widget_config.json
"""

from PyQt6.QtCore import Qt, QPoint, QRect, QRectF, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QObject
from PyQt6.QtGui import (
    QPainter, QPainterPath, QColor, QFont, QPen, QBrush,
    QLinearGradient, QAction, QCursor
)
from PyQt6.QtWidgets import (
    QWidget, QMenu, QApplication
)
import hardware_battery
from toast_manager import ToastManager
import threading
import json
import os
import sys
import time

CONFIG_FILE = os.path.join(
    os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)),
    "widget_config.json"
)


class BatteryUpdateWorker(QObject):
    data_ready = pyqtSignal(dict)

    def fetch(self):
        def _run():
            try:
                data = hardware_battery.get_all_devices_battery()
                self.data_ready.emit(data)
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()


class PlayStationBatteryWidget(QWidget):
    low_battery_alert = pyqtSignal(str, int)

    def __init__(self):
        super().__init__()

        # Window Flags: Frameless Desktop Widget (stays on desktop layer, tool window)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        # Widget Dimensions
        self.widget_width = 196
        self.row_single_h = 38
        self.row_double_h = 68
        self.current_target_h = self.row_double_h

        # State Data
        self.dualsense_data = {
            "connected": False,
            "name": "DualSense",
            "battery": 0,
            "charging": False,
            "full": False,
            "status_text": "Disconnected",
            "is_checking": False
        }
        self.pulse_data = {
            "connected": False,
            "name": "PULSE Elite",
            "battery": 0,
            "charging": False,
            "full": False,
            "status_text": "Disconnected",
            "is_checking": False
        }

        # Track previous states for toast notifications & morphing
        self.prev_ds_connected = None
        self.prev_ds_charging = None
        self.prev_pe_connected = None

        # Connection & Settling State Trackers (prevents premature 0% low-battery alerts)
        self.ds_checking = False
        self.ds_check_start_time = 0.0
        self.pe_checking = False
        self.pe_check_start_time = 0.0

        # User Visibility States
        self.desktop_widget_enabled = True   # If False, Tray-Only mode!
        self.user_hidden = False             # If True, temporarily hidden by tray click
        self.is_retracted = False

        # Config Settings
        self.theme = "light"
        self.low_battery_notifications_enabled = True
        self.connection_toasts_enabled = True
        self.auto_hide_when_disconnected = True
        self.notified_low = {"dualsense": False, "pulse_elite": False}

        # Docking & Position State
        self.dock_side = "right"
        self.drag_position = QPoint()
        self.is_dragging = False
        self.morph_anim = None

        # Set initial size
        self.resize(self.widget_width, self.row_double_h)

        # Polling Worker
        self.worker = BatteryUpdateWorker()
        self.worker.data_ready.connect(self.on_battery_data)

        # Auto refresh timer (every 3.5 seconds)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.request_update)
        self.poll_timer.start(3500)

        # Restore saved settings or default
        if not self.load_saved_settings():
            self.snap_to_edge("right", target_y=None, animated=False)

        # Initial fetch
        self.request_update()

    def request_update(self):
        self.worker.fetch()

    def get_active_devices(self):
        active = []
        if self.dualsense_data.get("connected"):
            active.append(("dualsense", self.dualsense_data))
        if self.pulse_data.get("connected"):
            active.append(("pulse", self.pulse_data))
        return active

    def on_battery_data(self, data):
        new_ds = data.get("dualsense", self.dualsense_data)
        new_pe = data.get("pulse_elite", self.pulse_data)

        curr_ds_conn = new_ds.get("connected", False)
        curr_ds_charg = new_ds.get("charging", False)
        curr_ds_batt = new_ds.get("battery", 0)
        curr_ds_full = new_ds.get("full", False)
        hw_ds_checking = new_ds.get("is_checking", False)

        needs_fast_poll = False

        # 1. DualSense Connection & Settling logic
        if curr_ds_conn:
            # Fresh connection event (transition from disconnected or initial startup)
            if self.prev_ds_connected is False or self.prev_ds_connected is None:
                self.ds_checking = True
                self.ds_check_start_time = time.time()

            # Evaluate checking state
            if self.ds_checking:
                # If real battery received (> 0) or controller is charging/full
                if curr_ds_batt > 0 or curr_ds_charg or curr_ds_full:
                    self.ds_checking = False
                elif time.time() - self.ds_check_start_time >= 10.0:
                    # Grace period timeout after 10s of 0% reading
                    self.ds_checking = False
                else:
                    self.ds_checking = True
                    needs_fast_poll = True
            elif hw_ds_checking and curr_ds_batt == 0 and not curr_ds_charg:
                self.ds_checking = True
                self.ds_check_start_time = time.time()
                needs_fast_poll = True
        else:
            self.ds_checking = False

        new_ds["is_checking"] = self.ds_checking

        # 2. PULSE Elite Connection & Settling logic
        curr_pe_conn = new_pe.get("connected", False)
        curr_pe_batt = new_pe.get("battery", 0)
        curr_pe_full = new_pe.get("full", False)
        hw_pe_checking = new_pe.get("is_checking", False)

        if curr_pe_conn:
            if (self.prev_pe_connected is False or self.prev_pe_connected is None) and curr_pe_batt == 0:
                self.pe_checking = True
                self.pe_check_start_time = time.time()

            if self.pe_checking:
                if curr_pe_batt > 0 or curr_pe_full:
                    self.pe_checking = False
                elif time.time() - self.pe_check_start_time >= 10.0:
                    self.pe_checking = False
                else:
                    self.pe_checking = True
                    needs_fast_poll = True
            elif hw_pe_checking and curr_pe_batt == 0:
                self.pe_checking = True
                self.pe_check_start_time = time.time()
                needs_fast_poll = True
        else:
            self.pe_checking = False

        new_pe["is_checking"] = self.pe_checking

        # 3. Connection Toast Notifications
        if self.prev_ds_connected is not None and self.connection_toasts_enabled:
            # Connect Event
            if not self.prev_ds_connected and curr_ds_conn:
                ToastManager.show_toast(
                    title="Controller has been connected.",
                    subtitle="DualSense Controller Status",
                    toast_type="connected",
                    theme=self.theme
                )
            # Disconnect Event
            elif self.prev_ds_connected and not curr_ds_conn:
                ToastManager.show_toast(
                    title="Controller disconnected.",
                    subtitle="DualSense Controller Status",
                    toast_type="disconnected",
                    theme=self.theme
                )
            # Unplug / Plug Transitions
            elif self.prev_ds_connected and curr_ds_conn:
                if self.prev_ds_charging is True and curr_ds_charg is False:
                    ToastManager.show_toast(
                        title="Controller is discharging.",
                        subtitle="DualSense Controller Status",
                        toast_type="discharging",
                        theme=self.theme
                    )
                elif self.prev_ds_charging is False and curr_ds_charg is True:
                    ToastManager.show_toast(
                        title="Controller is charging.",
                        subtitle="DualSense Controller Status",
                        toast_type="charging",
                        theme=self.theme
                    )

        self.prev_ds_connected = curr_ds_conn
        self.prev_ds_charging = curr_ds_charg

        # Pulse Elite Toasts
        if self.prev_pe_connected is not None and self.connection_toasts_enabled:
            if not self.prev_pe_connected and curr_pe_conn:
                ToastManager.show_toast(
                    title="Headset has been connected.",
                    subtitle="PULSE Elite Wireless",
                    toast_type="connected",
                    theme=self.theme
                )
            elif self.prev_pe_connected and not curr_pe_conn:
                ToastManager.show_toast(
                    title="Headset disconnected.",
                    subtitle="PULSE Elite Wireless",
                    toast_type="disconnected",
                    theme=self.theme
                )

        self.prev_pe_connected = curr_pe_conn

        self.dualsense_data = new_ds
        self.pulse_data = new_pe

        # 4. Check Low Battery Alerts (Only if NOT in 'Checking...' settling state!)
        if self.low_battery_notifications_enabled:
            self._check_low_battery("DualSense", self.dualsense_data, "dualsense")
            self._check_low_battery("PULSE Elite", self.pulse_data, "pulse_elite")

        # 5. Dynamic Auto Morphing (Only if desktop widget enabled AND not user-hidden!)
        if self.desktop_widget_enabled and not self.user_hidden and not self.is_dragging:
            self.apply_dynamic_morph()

        # Quick refresh if any device is in checking mode
        if needs_fast_poll:
            QTimer.singleShot(800, self.request_update)

        self.update()

    def user_toggle_visibility(self):
        """Called when user clicks Tray Icon or Show/Hide menu item."""
        if not self.desktop_widget_enabled:
            self.desktop_widget_enabled = True
            self.user_hidden = False
            self.save_settings()
            self.apply_dynamic_morph(force_show=True)
            return

        if self.isVisible() and not self.is_retracted and not self.user_hidden:
            self.user_hidden = True
            self.hide()
        else:
            self.user_hidden = False
            self.apply_dynamic_morph(force_show=True)

    def set_desktop_widget_enabled(self, enabled: bool):
        self.desktop_widget_enabled = enabled
        self.save_settings()
        if enabled:
            self.user_hidden = False
            self.apply_dynamic_morph(force_show=True)
        else:
            self.hide()

    def apply_dynamic_morph(self, force_show=False):
        if not self.desktop_widget_enabled:
            self.hide()
            return

        active = self.get_active_devices()
        count = len(active)
        screen = QApplication.primaryScreen().availableGeometry()
        w = self.widget_width

        if count == 0 and self.auto_hide_when_disconnected and not force_show:
            if not self.is_retracted:
                self.is_retracted = True
                curr_h = self.height()
                if self.dock_side == "right":
                    target_rect = QRect(screen.right() + 4, self.y(), w, curr_h)
                elif self.dock_side == "left":
                    target_rect = QRect(screen.left() - w - 4, self.y(), w, curr_h)
                elif self.dock_side == "top":
                    target_rect = QRect(self.x(), screen.top() - curr_h - 4, w, curr_h)
                elif self.dock_side == "bottom":
                    target_rect = QRect(self.x(), screen.bottom() + 4, w, curr_h)
                else:
                    target_rect = QRect(self.x(), self.y(), w, curr_h)

                self._animate_geometry(target_rect, on_finish=lambda: self.hide() if self.is_retracted else None)
            return

        # 1 or 2 devices active (or forced show)
        target_h = self.row_single_h if count == 1 else self.row_double_h
        self.current_target_h = target_h

        # Compute target position based on docking
        if self.dock_side == "right":
            target_x = screen.right() - w + 1
            target_y = max(screen.top(), min(self.y(), screen.bottom() - target_h + 1))
        elif self.dock_side == "left":
            target_x = screen.left()
            target_y = max(screen.top(), min(self.y(), screen.bottom() - target_h + 1))
        elif self.dock_side == "top":
            target_x = max(screen.left(), min(self.x(), screen.right() - w + 1))
            target_y = screen.top()
        elif self.dock_side == "bottom":
            target_x = max(screen.left(), min(self.x(), screen.right() - w + 1))
            target_y = screen.bottom() - target_h + 1
        else:
            target_x = max(screen.left(), min(self.x(), screen.right() - w + 1))
            target_y = max(screen.top(), min(self.y(), screen.bottom() - target_h + 1))

        target_rect = QRect(target_x, target_y, w, target_h)

        if self.is_retracted or not self.isVisible():
            self.is_retracted = False
            self.show()
            self._animate_geometry(target_rect)
        elif self.height() != target_h:
            self._animate_geometry(target_rect)

    def _animate_geometry(self, target_rect: QRect, duration_ms: int = 300, on_finish=None):
        if self.morph_anim is not None and self.morph_anim.state() == QPropertyAnimation.State.Running:
            self.morph_anim.stop()

        self.morph_anim = QPropertyAnimation(self, b"geometry")
        self.morph_anim.setDuration(duration_ms)
        self.morph_anim.setStartValue(self.geometry())
        self.morph_anim.setEndValue(target_rect)
        self.morph_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        if on_finish:
            self.morph_anim.finished.connect(on_finish)
        self.morph_anim.start()

    def _check_low_battery(self, name: str, data: dict, key: str):
        connected = data.get("connected", False)
        battery = data.get("battery", 100)
        charging = data.get("charging", False)
        is_checking = data.get("is_checking", False)

        # Do NOT send low battery notification while checking / settling!
        if is_checking:
            return

        if connected and not charging and battery <= 20:
            if not self.notified_low[key]:
                self.low_battery_alert.emit(name, battery)
                self.notified_low[key] = True
        else:
            if charging or battery > 20 or not connected:
                self.notified_low[key] = False

    def save_settings(self):
        cfg = {
            "x": self.x(),
            "y": self.y(),
            "dock_side": self.dock_side,
            "theme": self.theme,
            "low_battery_alerts": self.low_battery_notifications_enabled,
            "connection_toasts": self.connection_toasts_enabled,
            "auto_hide": self.auto_hide_when_disconnected,
            "desktop_widget_enabled": self.desktop_widget_enabled
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    def load_saved_settings(self) -> bool:
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                screen = QApplication.primaryScreen().availableGeometry()
                x = max(screen.left(), min(cfg.get("x", 0), screen.right() - self.widget_width))
                y = max(screen.top(), min(cfg.get("y", 0), screen.bottom() - self.row_double_h))
                self.dock_side = cfg.get("dock_side", "none")
                self.theme = cfg.get("theme", "light")
                self.low_battery_notifications_enabled = cfg.get("low_battery_alerts", True)
                self.connection_toasts_enabled = cfg.get("connection_toasts", True)
                self.auto_hide_when_disconnected = cfg.get("auto_hide", True)
                self.desktop_widget_enabled = cfg.get("desktop_widget_enabled", True)
                self.move(x, y)
                if not self.desktop_widget_enabled:
                    self.hide()
                return True
        except Exception:
            pass
        return False

    def snap_to_edge(self, edge: str, target_x=None, target_y=None, animated=True):
        screen = QApplication.primaryScreen().availableGeometry()
        min_x = screen.left()
        max_x = screen.right() - self.widget_width + 1
        h = self.height()
        min_y = screen.top()
        max_y = screen.bottom() - h + 1

        curr_x = self.x() if target_x is None else target_x
        curr_y = self.y() if target_y is None else target_y

        if edge == "right":
            dest_x = max_x
            dest_y = max(min_y, min(curr_y, max_y))
            self.dock_side = "right"
        elif edge == "left":
            dest_x = min_x
            dest_y = max(min_y, min(curr_y, max_y))
            self.dock_side = "left"
        elif edge == "top":
            dest_x = max(min_x, min(curr_x, max_x))
            dest_y = min_y
            self.dock_side = "top"
        elif edge == "bottom":
            dest_x = max(min_x, min(curr_x, max_x))
            dest_y = max_y
            self.dock_side = "bottom"
        else:
            dest_x = max(min_x, min(curr_x, max_x))
            dest_y = max(min_y, min(curr_y, max_y))
            self.dock_side = "none"

        target_rect = QRect(dest_x, dest_y, self.widget_width, h)
        if animated:
            self._animate_geometry(target_rect, on_finish=self.save_settings)
        else:
            self.setGeometry(target_rect)
            self.save_settings()

        self.update()

    def check_magnetic_snap(self, animated=True):
        screen = QApplication.primaryScreen().availableGeometry()
        threshold = 60

        x = self.x()
        y = self.y()
        w = self.widget_width
        h = self.height()

        dist_left = abs(x - screen.left())
        dist_right = abs((x + w) - (screen.right() + 1))
        dist_top = abs(y - screen.top())
        dist_bottom = abs((y + h) - (screen.bottom() + 1))

        min_dist = min(dist_left, dist_right, dist_top, dist_bottom)

        if min_dist <= threshold:
            if min_dist == dist_right:
                self.snap_to_edge("right", animated=animated)
            elif min_dist == dist_left:
                self.snap_to_edge("left", animated=animated)
            elif min_dist == dist_top:
                self.snap_to_edge("top", animated=animated)
            else:
                self.snap_to_edge("bottom", animated=animated)
        else:
            self.dock_side = "none"
            clamped_x = max(screen.left(), min(x, screen.right() - w))
            clamped_y = max(screen.top(), min(y, screen.bottom() - h))
            if (clamped_x, clamped_y) != (x, y):
                self.move(clamped_x, clamped_y)
            self.save_settings()
            self.update()

    # Mouse Events
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self.drag_position
            self.move(new_pos)

            screen = QApplication.primaryScreen().availableGeometry()
            x, y = self.x(), self.y()
            w, h = self.widget_width, self.height()

            if abs((x + w) - (screen.right() + 1)) <= 15:
                curr_dock = "right"
            elif abs(x - screen.left()) <= 15:
                curr_dock = "left"
            elif abs(y - screen.top()) <= 15:
                curr_dock = "top"
            elif abs((y + h) - (screen.bottom() + 1)) <= 15:
                curr_dock = "bottom"
            else:
                curr_dock = "none"

            if curr_dock != self.dock_side:
                self.dock_side = curr_dock
                self.update()

            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            self.check_magnetic_snap(animated=True)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.check_magnetic_snap(animated=True)
            event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        is_dark = (self.theme == "dark")

        if is_dark:
            menu.setStyleSheet("""
                QMenu {
                    background-color: #1e222d;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 4px;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: 12px;
                    color: #f1f5f9;
                }
                QMenu::item {
                    padding: 6px 20px;
                    border-radius: 4px;
                }
                QMenu::item:selected {
                    background-color: #0070d1;
                    color: white;
                }
                QMenu::separator {
                    height: 1px;
                    background-color: #334155;
                    margin: 4px 6px;
                }
            """)
        else:
            menu.setStyleSheet("""
                QMenu {
                    background-color: rgba(255, 255, 255, 0.96);
                    border: 1px solid rgba(200, 200, 200, 0.6);
                    border-radius: 8px;
                    padding: 4px;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: 12px;
                    color: #1e293b;
                }
                QMenu::item {
                    padding: 6px 20px;
                    border-radius: 4px;
                }
                QMenu::item:selected {
                    background-color: #0070d1;
                    color: white;
                }
                QMenu::separator {
                    height: 1px;
                    background-color: rgba(220, 220, 220, 0.8);
                    margin: 4px 6px;
                }
            """)

        # Snap Submenu
        snap_menu = menu.addMenu("Snap to Edge")
        snap_menu.addAction("Right Edge").triggered.connect(lambda: self.snap_to_edge("right"))
        snap_menu.addAction("Left Edge").triggered.connect(lambda: self.snap_to_edge("left"))
        snap_menu.addAction("Top Edge").triggered.connect(lambda: self.snap_to_edge("top"))
        snap_menu.addAction("Bottom Edge").triggered.connect(lambda: self.snap_to_edge("bottom"))

        # Theme Submenu
        theme_menu = menu.addMenu("Theme")
        light_act = theme_menu.addAction("Light Theme")
        light_act.setCheckable(True)
        light_act.setChecked(self.theme == "light")
        light_act.triggered.connect(lambda: self.set_theme("light"))

        dark_act = theme_menu.addAction("Dark Theme")
        dark_act.setCheckable(True)
        dark_act.setChecked(self.theme == "dark")
        dark_act.triggered.connect(lambda: self.set_theme("dark"))

        # Auto-hide toggle
        auto_hide_action = menu.addAction("Auto-Retract when Disconnected")
        auto_hide_action.setCheckable(True)
        auto_hide_action.setChecked(self.auto_hide_when_disconnected)
        auto_hide_action.triggered.connect(self.toggle_autohide)

        # Connection Toasts Toggle
        toast_act = menu.addAction("Connection Toast Alerts")
        toast_act.setCheckable(True)
        toast_act.setChecked(self.connection_toasts_enabled)
        toast_act.triggered.connect(self.toggle_connection_toasts)

        # Low Battery Alert Toggle
        alert_act = menu.addAction("Low Battery Alert (<=20%)")
        alert_act.setCheckable(True)
        alert_act.setChecked(self.low_battery_notifications_enabled)
        alert_act.triggered.connect(self.toggle_low_battery_alerts)

        refresh_action = menu.addAction("Refresh Status Now")
        refresh_action.triggered.connect(self.request_update)

        menu.addSeparator()

        hide_action = menu.addAction("Hide to System Tray")
        hide_action.triggered.connect(self.user_toggle_visibility)

        quit_action = menu.addAction("Exit PSBatteryWidget")
        quit_action.triggered.connect(QApplication.instance().quit)

        menu.exec(event.globalPos())

    def toggle_autohide(self, checked):
        self.auto_hide_when_disconnected = checked
        self.save_settings()
        self.apply_dynamic_morph()

    def toggle_connection_toasts(self, checked):
        self.connection_toasts_enabled = checked
        self.save_settings()

    def toggle_low_battery_alerts(self, checked):
        self.low_battery_notifications_enabled = checked
        self.save_settings()

    def set_theme(self, theme_name: str):
        self.theme = theme_name
        self.save_settings()
        self.update()

    def toggle_theme(self):
        self.set_theme("dark" if self.theme == "light" else "light")

    def show_full_widget(self):
        self.is_retracted = False
        self.show()

    # Dynamic Drawing based on Active Devices, Theme, and Dock Edge
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = float(self.width())
        h = float(self.height())
        if w < 10 or h < 10:
            return

        radius = 12.0
        is_dark = (self.theme == "dark")

        card_path = QPainterPath()

        if self.dock_side == "right":
            card_path.moveTo(w, 0.5)
            card_path.lineTo(radius, 0.5)
            card_path.arcTo(QRectF(0.5, 0.5, radius * 2, radius * 2), 90, 90)
            card_path.lineTo(0.5, h - radius - 0.5)
            card_path.arcTo(QRectF(0.5, h - radius * 2 - 0.5, radius * 2, radius * 2), 180, 90)
            card_path.lineTo(w, h - 0.5)
            card_path.closeSubpath()

        elif self.dock_side == "left":
            card_path.moveTo(0.5, 0.5)
            card_path.lineTo(w - radius - 0.5, 0.5)
            card_path.arcTo(QRectF(w - radius * 2 - 0.5, 0.5, radius * 2, radius * 2), 90, -90)
            card_path.lineTo(w - 0.5, h - radius - 0.5)
            card_path.arcTo(QRectF(w - radius * 2 - 0.5, h - radius * 2 - 0.5, radius * 2, radius * 2), 0, -90)
            card_path.lineTo(0.5, h - 0.5)
            card_path.closeSubpath()

        elif self.dock_side == "top":
            card_path.moveTo(0.5, 0.5)
            card_path.lineTo(w - 0.5, 0.5)
            card_path.lineTo(w - 0.5, h - radius - 0.5)
            card_path.arcTo(QRectF(w - radius * 2 - 0.5, h - radius * 2 - 0.5, radius * 2, radius * 2), 0, -90)
            card_path.lineTo(radius, h - 0.5)
            card_path.arcTo(QRectF(0.5, h - radius * 2 - 0.5, radius * 2, radius * 2), 270, -90)
            card_path.closeSubpath()

        elif self.dock_side == "bottom":
            card_path.moveTo(0.5, h - 0.5)
            card_path.lineTo(w - 0.5, h - 0.5)
            card_path.lineTo(w - 0.5, radius + 0.5)
            card_path.arcTo(QRectF(w - radius * 2 - 0.5, 0.5, radius * 2, radius * 2), 0, 90)
            card_path.lineTo(radius, 0.5)
            card_path.arcTo(QRectF(0.5, 0.5, radius * 2, radius * 2), 90, 90)
            card_path.closeSubpath()

        else:
            card_path.addRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), radius, radius)

        # Background Fill
        if is_dark:
            bg_brush = QBrush(QColor(22, 26, 36, 246))
            border_pen = QPen(QColor(51, 65, 85, 200), 1.0)
        else:
            bg_brush = QBrush(QColor(248, 250, 252, 246))
            border_pen = QPen(QColor(203, 213, 225, 220), 1.0)

        painter.fillPath(card_path, bg_brush)
        painter.setPen(border_pen)
        painter.drawPath(card_path)

        # Left edge accent bar (PlayStation Blue #0070d1)
        accent_x = (w - 3.5) if self.dock_side == "left" else (1.5 if self.dock_side == "right" else 1.5)
        accent_path = QPainterPath()
        accent_path.addRoundedRect(QRectF(accent_x, 10, 2.5, h - 20), 1.25, 1.25)
        painter.fillPath(accent_path, QColor(0, 112, 209))

        # Device Rows Rendering
        active = self.get_active_devices()
        count = len(active)

        if count == 2:
            sep_color = QColor(51, 65, 85, 160) if is_dark else QColor(226, 232, 240, 180)
            painter.setPen(QPen(sep_color, 0.8))
            painter.drawLine(14, int(h / 2), int(w - 10), int(h / 2))

            dev1_type, dev1_data = active[0]
            dev2_type, dev2_data = active[1]
            self.draw_device_row(painter, 6, dev1_type, dev1_data["name"], dev1_data["connected"],
                                dev1_data["battery"], dev1_data["charging"], is_dark,
                                is_checking=dev1_data.get("is_checking", False))
            self.draw_device_row(painter, 36, dev2_type, dev2_data["name"], dev2_data["connected"],
                                dev2_data["battery"], dev2_data["charging"], is_dark,
                                is_checking=dev2_data.get("is_checking", False))

        elif count == 1:
            dev_type, dev_data = active[0]
            y_cen = int((h - 24) / 2)
            self.draw_device_row(painter, y_cen, dev_type, dev_data["name"], dev_data["connected"],
                                dev_data["battery"], dev_data["charging"], is_dark,
                                is_checking=dev_data.get("is_checking", False))

        else:
            sep_color = QColor(51, 65, 85, 160) if is_dark else QColor(226, 232, 240, 180)
            painter.setPen(QPen(sep_color, 0.8))
            painter.drawLine(14, int(h / 2), int(w - 10), int(h / 2))
            self.draw_device_row(painter, 6, "dualsense", "DualSense", False, 0, False, is_dark, is_checking=False)
            self.draw_device_row(painter, 36, "pulse", "PULSE Elite", False, 0, False, is_dark, is_checking=False)

    def draw_device_row(self, painter: QPainter, y_offset: int, device_type: str,
                        name: str, connected: bool, battery: int, charging: bool, is_dark: bool,
                        is_checking: bool = False):
        icon_x = 15 if self.dock_side == "right" else 12
        icon_y = y_offset + 2

        if device_type == "dualsense":
            self.draw_controller_icon(painter, icon_x, icon_y, connected, is_dark)
        else:
            self.draw_headset_icon(painter, icon_x, icon_y, connected, is_dark)

        font_name = QFont("Segoe UI", 9)
        font_name.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font_name)
        text_color = (QColor(241, 245, 249) if is_dark else QColor(30, 41, 59)) if connected else (QColor(100, 116, 139) if is_dark else QColor(148, 163, 184))
        painter.setPen(text_color)
        painter.drawText(icon_x + 19, y_offset + 15, name)

        right_margin = 12 if self.dock_side == "left" else 8
        if connected:
            if is_checking:
                # Modern stylish 'Checking...' indicator in PlayStation Blue accent
                font_check = QFont("Segoe UI", 8)
                font_check.setWeight(QFont.Weight.Medium)
                painter.setFont(font_check)
                check_color = QColor(56, 189, 248) if is_dark else QColor(0, 112, 209)
                painter.setPen(check_color)
                check_rect = QRect(self.width() - 72 - right_margin, y_offset + 2, 70, 16)
                painter.drawText(check_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "Checking...")
            else:
                if charging:
                    level_color = QColor(245, 158, 11)
                elif battery > 50:
                    level_color = QColor(34, 197, 94) if is_dark else QColor(16, 185, 129)
                elif battery > 20:
                    level_color = QColor(245, 158, 11)
                else:
                    level_color = QColor(239, 68, 68)

                font_pct = QFont("Segoe UI", 9)
                font_pct.setWeight(QFont.Weight.Bold)
                painter.setFont(font_pct)
                painter.setPen(level_color)

                pct_str = f"{battery}%"
                pct_rect = QRect(self.width() - 38 - right_margin, y_offset + 2, 36, 16)
                painter.drawText(pct_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, pct_str)

                batt_x = self.width() - 64 - right_margin
                batt_y = y_offset + 5
                self.draw_battery_capsule(painter, batt_x, batt_y, battery, charging, level_color, is_dark)
        else:
            font_off = QFont("Segoe UI", 8)
            painter.setFont(font_off)
            painter.setPen(QColor(100, 116, 139) if is_dark else QColor(160, 174, 192))
            off_rect = QRect(self.width() - 48 - right_margin, y_offset + 2, 46, 16)
            painter.drawText(off_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "Off")

    def draw_controller_icon(self, painter: QPainter, x: int, y: int, connected: bool, is_dark: bool):
        color = (QColor(226, 232, 240) if is_dark else QColor(51, 65, 85)) if connected else (QColor(100, 116, 139) if is_dark else QColor(160, 174, 192))
        pen = QPen(color, 1.25, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        body = QPainterPath()
        body.moveTo(x + 2, y + 5)
        body.quadTo(x + 7.5, y + 2.5, x + 13, y + 5)
        body.quadTo(x + 15, y + 9, x + 14, y + 14)
        body.quadTo(x + 11.5, y + 13, x + 10, y + 10.5)
        body.quadTo(x + 7.5, y + 11.5, x + 5, y + 10.5)
        body.quadTo(x + 3.5, y + 13, x + 1, y + 14)
        body.quadTo(x, y + 9, x + 2, y + 5)
        painter.drawPath(body)

        painter.setBrush(color)
        painter.drawEllipse(QRectF(x + 4.5, y + 8, 1.3, 1.3))
        painter.drawEllipse(QRectF(x + 9.5, y + 8, 1.3, 1.3))

    def draw_headset_icon(self, painter: QPainter, x: int, y: int, connected: bool, is_dark: bool):
        color = (QColor(226, 232, 240) if is_dark else QColor(51, 65, 85)) if connected else (QColor(100, 116, 139) if is_dark else QColor(160, 174, 192))
        pen = QPen(color, 1.25, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        band = QPainterPath()
        band.arcMoveTo(QRectF(x + 1, y + 2, 13, 13), 0)
        band.arcTo(QRectF(x + 1, y + 2, 13, 13), 0, 180)
        painter.drawPath(band)

        cup_pen = QPen(color, 1.0)
        painter.setPen(cup_pen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(x + 0.5, y + 8, 2.5, 6), 1.2, 1.2)
        painter.drawRoundedRect(QRectF(x + 12.0, y + 8, 2.5, 6), 1.2, 1.2)

    def draw_battery_capsule(self, painter: QPainter, x: int, y: int, pct: int, charging: bool, color: QColor, is_dark: bool):
        w = 20
        h = 10

        border_col = QColor(100, 116, 139, 180) if is_dark else QColor(148, 163, 184, 180)
        pen = QPen(border_col, 1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(x, y, w, h), 2.5, 2.5)

        tip_pen = QPen(border_col, 1.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(tip_pen)
        painter.drawLine(x + w + 1, y + 3, x + w + 1, y + h - 3)

        inner_w = (w - 3) * (min(max(pct, 0), 100) / 100.0)
        if inner_w > 1.0:
            fill_rect = QRectF(x + 1.5, y + 1.5, inner_w, h - 3.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(fill_rect, 1.5, 1.5)

        if charging:
            painter.setPen(QPen(QColor(255, 255, 255) if is_dark else QColor(15, 23, 42), 1.0))
            bolt = QPainterPath()
            bx = x + (w / 2.0) - 2.5
            by = y + 1
            bolt.moveTo(bx + 3.0, by + 1)
            bolt.lineTo(bx + 0.5, by + 4.5)
            bolt.lineTo(bx + 3.5, by + 4.5)
            bolt.lineTo(bx + 1.5, by + 8)
            painter.drawPath(bolt)
