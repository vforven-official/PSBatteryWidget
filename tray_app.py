"""
tray_app.py
System Tray integration for PSBatteryWidget.
Manages application lifecycle, tray icon, tooltip, context menu,
theme switching, toast notifications, low battery notifications, and Windows Startup registry.
"""

import sys
import os
import winreg
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QAction, QPainterPath
from PyQt6.QtCore import Qt, QRectF, QPoint


RUN_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_REG_NAME = "PSBatteryWidget"
LEGACY_REG_NAME = "PlayStationBatteryWidget"


def is_run_at_startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_REG_NAME)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def set_run_at_startup(enable: bool):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            # Always remove any legacy duplicate entry
            try:
                winreg.DeleteValue(key, LEGACY_REG_NAME)
            except FileNotFoundError:
                pass

            if enable:
                if getattr(sys, 'frozen', False):
                    exe_path = f'"{sys.executable}"'
                else:
                    exe_path = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
                winreg.SetValueEx(key, APP_REG_NAME, 0, winreg.REG_SZ, exe_path)
            else:
                try:
                    winreg.DeleteValue(key, APP_REG_NAME)
                except FileNotFoundError:
                    pass
    except Exception as e:
        print("Failed to set startup registry key:", e)


def create_tray_icon_pixmap() -> QPixmap:
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    x0, y0 = 3, 10
    x1, y1 = 53, 54
    painter.setPen(QPen(QColor(255, 255, 255), 5.0))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(x0, y0, x1 - x0, y1 - y0), 9.0, 9.0)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255))
    painter.drawRoundedRect(QRectF(x1 + 2, y0 + 11, 6, (y1 - y0) - 22), 3.0, 3.0)

    bolt = QPainterPath()
    bolt.moveTo(32, 14)
    bolt.lineTo(18, 33)
    bolt.lineTo(28, 33)
    bolt.lineTo(24, 50)
    bolt.lineTo(40, 29)
    bolt.lineTo(30, 29)
    bolt.closeSubpath()
    painter.drawPath(bolt)

    painter.end()
    return pixmap


class PlayStationTray(QSystemTrayIcon):
    def __init__(self, widget):
        super().__init__()
        self.widget = widget

        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        tray_ico = os.path.join(base_dir, "tray_white_charging.ico")
        tray_png = os.path.join(base_dir, "tray_white_charging.png")

        if os.path.exists(tray_ico):
            self.setIcon(QIcon(tray_ico))
        elif os.path.exists(tray_png):
            self.setIcon(QIcon(tray_png))
        else:
            self.setIcon(QIcon(create_tray_icon_pixmap()))

        self.setToolTip("PSBatteryWidget")

        self.menu = QMenu()
        self.build_menu()
        self.setContextMenu(self.menu)

        self.activated.connect(self.on_activated)
        self.widget.worker.data_ready.connect(self.update_battery_status)
        self.widget.low_battery_alert.connect(self.on_low_battery_alert)

    def build_menu(self):
        self.menu.clear()

        is_dark = (self.widget.theme == "dark")
        if is_dark:
            self.menu.setStyleSheet("""
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
                    padding: 6px 22px;
                    border-radius: 4px;
                }
                QMenu::item:selected {
                    background-color: #0070d1;
                    color: #ffffff;
                }
                QMenu::separator {
                    height: 1px;
                    background-color: #334155;
                    margin: 4px 6px;
                }
            """)
        else:
            self.menu.setStyleSheet("""
                QMenu {
                    background-color: #ffffff;
                    border: 1px solid #d1d5db;
                    border-radius: 8px;
                    padding: 4px;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: 12px;
                    color: #1f2937;
                }
                QMenu::item {
                    padding: 6px 22px;
                    border-radius: 4px;
                }
                QMenu::item:selected {
                    background-color: #0070d1;
                    color: #ffffff;
                }
                QMenu::separator {
                    height: 1px;
                    background-color: #e5e7eb;
                    margin: 4px 6px;
                }
            """)

        self.toggle_action = self.menu.addAction("Show / Hide Widget")
        self.toggle_action.triggered.connect(self.toggle_widget)

        # Show Desktop Widget Toggle (Tray-Only Mode)
        self.widget_enable_action = self.menu.addAction("Show Desktop Widget")
        self.widget_enable_action.setCheckable(True)
        self.widget_enable_action.setChecked(self.widget.desktop_widget_enabled)
        self.widget_enable_action.triggered.connect(self.toggle_desktop_widget)

        self.menu.addSeparator()

        self.snap_menu = self.menu.addMenu("Snap to Edge")
        self.snap_menu.addAction("Right Edge").triggered.connect(lambda: self.widget.snap_to_edge("right"))
        self.snap_menu.addAction("Left Edge").triggered.connect(lambda: self.widget.snap_to_edge("left"))
        self.snap_menu.addAction("Top Edge").triggered.connect(lambda: self.widget.snap_to_edge("top"))
        self.snap_menu.addAction("Bottom Edge").triggered.connect(lambda: self.widget.snap_to_edge("bottom"))

        # Theme Submenu
        self.theme_menu = self.menu.addMenu("Theme")
        light_act = self.theme_menu.addAction("Light Theme")
        light_act.setCheckable(True)
        light_act.setChecked(self.widget.theme == "light")
        light_act.triggered.connect(lambda: self.switch_theme("light"))

        dark_act = self.theme_menu.addAction("Dark Theme")
        dark_act.setCheckable(True)
        dark_act.setChecked(self.widget.theme == "dark")
        dark_act.triggered.connect(lambda: self.switch_theme("dark"))

        # Auto Retract Toggle
        self.autohide_action = self.menu.addAction("Auto-Retract when Disconnected")
        self.autohide_action.setCheckable(True)
        self.autohide_action.setChecked(self.widget.auto_hide_when_disconnected)
        self.autohide_action.triggered.connect(self.toggle_autohide)

        # Toast Notifications Toggle
        self.toast_action = self.menu.addAction("Connection Toast Alerts")
        self.toast_action.setCheckable(True)
        self.toast_action.setChecked(self.widget.connection_toasts_enabled)
        self.toast_action.triggered.connect(self.toggle_toasts)

        # Low Battery Alert
        self.alert_action = self.menu.addAction("Low Battery Alert (<=20%)")
        self.alert_action.setCheckable(True)
        self.alert_action.setChecked(self.widget.low_battery_notifications_enabled)
        self.alert_action.triggered.connect(self.toggle_low_battery)

        self.refresh_action = self.menu.addAction("Refresh Status Now")
        self.refresh_action.triggered.connect(self.widget.request_update)

        self.menu.addSeparator()

        self.startup_action = self.menu.addAction("Start with Windows")
        self.startup_action.setCheckable(True)
        self.startup_action.setChecked(is_run_at_startup_enabled())
        self.startup_action.triggered.connect(self.toggle_startup)

        self.menu.addSeparator()

        self.quit_action = self.menu.addAction("Exit")
        self.quit_action.triggered.connect(QApplication.instance().quit)

    def switch_theme(self, theme_name: str):
        self.widget.set_theme(theme_name)
        self.build_menu()

    def toggle_desktop_widget(self, checked):
        self.widget.set_desktop_widget_enabled(checked)
        self.build_menu()

    def toggle_autohide(self, checked):
        self.widget.toggle_autohide(checked)
        self.build_menu()

    def toggle_toasts(self, checked):
        self.widget.toggle_connection_toasts(checked)
        self.build_menu()

    def toggle_low_battery(self, checked):
        self.widget.toggle_low_battery_alerts(checked)
        self.build_menu()

    def on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_widget()

    def toggle_widget(self):
        self.widget.user_toggle_visibility()
        self.build_menu()

    def toggle_startup(self, checked):
        set_run_at_startup(checked)

    def update_battery_status(self, data):
        ds = data.get("dualsense", {})
        pe = data.get("pulse_elite", {})

        if ds.get("connected"):
            if ds.get("is_checking"):
                ds_str = "DualSense: Checking..."
            else:
                ds_str = f"DualSense: {ds.get('battery', 0)}%"
        else:
            ds_str = "DualSense: Off"

        if pe.get("connected"):
            if pe.get("is_checking"):
                pe_str = "PULSE Elite: Checking..."
            else:
                pe_str = f"PULSE Elite: {pe.get('battery', 0)}%"
        else:
            pe_str = "PULSE Elite: Off"

        self.setToolTip(f"PSBatteryWidget\n{ds_str}\n{pe_str}")

    def on_low_battery_alert(self, device_name: str, battery_pct: int):
        self.showMessage(
            f"Low Battery: {device_name}",
            f"{device_name} battery is low ({battery_pct}%). Connect charger to keep playing!",
            QSystemTrayIcon.MessageIcon.Warning,
            6000
        )
