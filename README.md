# PSBatteryWidget

A compact Windows desktop widget and system tray app for checking the battery status of PlayStation accessories.

## Download and run (Windows)

**[Download PSBatteryWidget v1.0.0 (.exe)](https://github.com/vforven-official/PSBatteryWidget/releases/download/v1.0.0/PSBatteryWidget.exe)**

The ready-to-run Windows app is available on the **[Releases page](https://github.com/vforven-official/PSBatteryWidget/releases/latest)**. No Python installation or build step is needed.

1. Download `PSBatteryWidget.exe` from the release's **Assets** section.
2. Place it in a permanent folder you can write to, then double-click it to run.
3. Connect your supported accessory and use the system tray icon to show the widget or change settings.

Your preferences are saved beside the executable in `widget_config.json`. Use the tray menu's **Exit** option to close the app.

## Features

- DualSense and DualSense Edge battery readings over USB or Bluetooth.
- PULSE Elite battery readings through the Bluetooth battery information exposed by Windows.
- Light and dark themes, draggable positioning, and snapping to all four screen edges.
- Automatic resizing for connected devices and optional retraction when disconnected.
- Desktop widget or tray-only operation, with battery status in the tray tooltip.
- Connection and controller charging alerts, plus low-battery notifications at 20% or below.
- Optional startup with Windows and saved preferences.
- Single-instance protection.

## Run from source

The app requires Windows and Python. The dependency versions below were checked with Python 3.14.

Download and extract this repository, or clone it, then open PowerShell in the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Connect a supported controller using USB or Bluetooth. For PULSE Elite, pair the headset through Windows Bluetooth; readings depend on Windows exposing its battery property. PlayStation Link USB adapter battery reporting is not implemented.

## Use the widget

Drag the widget to position it. Right-click the widget or its system tray icon to change the theme, docking, alerts, and visibility. Click the tray icon to show or hide the widget. Choose **Exit** in the tray menu to quit.

**Start with Windows** is an optional tray-menu setting. Enable it after placing the app in its permanent location; if you move it later, toggle the setting off and on to update its startup path.

Preferences are saved automatically to `widget_config.json` beside the source files or packaged executable. Keep the app in a folder you can write to. This personal configuration file is intentionally excluded from Git.

## Build a Windows executable

Run these commands on Windows from the project folder:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm PSBatteryWidget.spec
```

The executable is created at `dist\PSBatteryWidget.exe`. The build specification bundles the required icons and Python dependencies. Build outputs and executable files are excluded from the source repository.

## Project files

| File | Purpose |
| --- | --- |
| `main.py` | Application entry point and single-instance handling |
| `battery_widget.py` | Desktop widget, preferences, and battery state updates |
| `hardware_battery.py` | HID controller reads and Windows Bluetooth battery queries |
| `tray_app.py` | System tray menu, notifications, and optional Windows startup |
| `toast_manager.py` | Custom toast notification windows |
| `PSBatteryWidget.spec` | PyInstaller build configuration |
| `app_icon.*`, `tray_white_charging.*` | Application and system tray assets |

## Device limitations

The current reader handles the first detected supported controller and one PULSE headset entry. Battery percentages depend on device reports and Windows Bluetooth properties; they may update in steps. A newly connected device can briefly show **Checking...** before a reading becomes available. Hardware compatibility can vary with firmware, drivers, and connection mode.
