"""
main.py
Entry point for the PlayStation Battery Widget application.
Initializes the Single Instance Mutex, Qt Application, Desktop Floating Widget, and System Tray icon.
"""

import sys
import os
import ctypes
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from battery_widget import PlayStationBatteryWidget
from tray_app import PlayStationTray, create_tray_icon_pixmap

# Windows Named Mutex for strict Single Instance enforcement
MUTEX_NAME = "Global\\PSBatteryWidget_SingleInstance_Mutex_v1"
ERROR_ALREADY_EXISTS = 183


def ensure_single_instance():
    """
    Ensures only one instance of the application runs at any given time.
    If an instance is already running, exits immediately with code 0.
    """
    if sys.platform == 'win32':
        try:
            mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
            last_error = ctypes.windll.kernel32.GetLastError()
            if last_error == ERROR_ALREADY_EXISTS or not mutex:
                # Another instance is already running!
                sys.exit(0)
            return mutex
        except Exception:
            pass
    return None


def main():
    # 1. Enforce strict Single Instance
    mutex = ensure_single_instance()

    # 2. Set Windows App User Model ID so notifications and tray group properly
    if sys.platform == 'win32':
        try:
            myappid = 'psbatterywidget.v1'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("PSBatteryWidget")
    app.setOrganizationName("Antigravity")

    # Crucial: Don't exit when widget is hidden to tray
    app.setQuitOnLastWindowClosed(False)

    # Set Application Icon
    ico_path = os.path.join(os.path.dirname(__file__), "app_icon.ico")
    if os.path.exists(ico_path):
        app_icon = QIcon(ico_path)
    else:
        app_icon = QIcon(create_tray_icon_pixmap())
    app.setWindowIcon(app_icon)

    # Create Widget
    widget = PlayStationBatteryWidget()
    widget.show()

    # Create Tray
    tray = PlayStationTray(widget)
    tray.show()

    exit_code = app.exec()

    if mutex and sys.platform == 'win32':
        try:
            ctypes.windll.kernel32.CloseHandle(mutex)
        except Exception:
            pass

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
