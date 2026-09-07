"""
toast_manager.py
Custom Windows Flyout / Toast Notification widget matching PS5 / Windows 11 style.
Displays sleek, animated toast notifications when:
- Controller connects via USB or Bluetooth
- Controller is unplugged (discharging)
- Controller is plugged in (charging)
- Controller is disconnected
"""

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QRectF, QPoint, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import (
    QPainter, QPainterPath, QColor, QFont, QPen, QBrush
)

class ToastNotification(QWidget):
    def __init__(self, title: str, subtitle: str, toast_type: str = "connected", theme: str = "light", duration_ms: int = 3500):
        super().__init__()
        self.title = title
        self.subtitle = subtitle
        self.toast_type = toast_type
        self.theme = theme
        self.duration_ms = duration_ms

        # Frameless, Tool Window, Always on Top, Non-activating so it doesn't steal focus from games
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.setFixedSize(246, 56)

        # Position at bottom-right corner of screen (above taskbar)
        screen = QApplication.primaryScreen().availableGeometry()
        margin_x = 20
        margin_y = 20
        self.target_x = screen.right() - self.width() - margin_x
        self.target_y = screen.bottom() - self.height() - margin_y
        self.move(self.target_x, self.target_y)

        # Fade in animation
        self.setWindowOpacity(0.0)
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(250)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Dismiss timer
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.fade_out)

    def show_animated(self):
        self.show()
        self.fade_anim.start()
        self.dismiss_timer.start(self.duration_ms)

    def fade_out(self):
        self.out_anim = QPropertyAnimation(self, b"windowOpacity")
        self.out_anim.setDuration(280)
        self.out_anim.setStartValue(self.windowOpacity())
        self.out_anim.setEndValue(0.0)
        self.out_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self.out_anim.finished.connect(self.close)
        self.out_anim.start()

    def mousePressEvent(self, event):
        self.fade_out()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = float(self.width())
        h = float(self.height())
        radius = 10.0
        is_dark = (self.theme == "dark")

        # 1. Background Card
        card_rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        card_path = QPainterPath()
        card_path.addRoundedRect(card_rect, radius, radius)

        if is_dark:
            bg_brush = QBrush(QColor(28, 33, 46, 248))
            border_pen = QPen(QColor(60, 72, 98, 220), 1.0)
        else:
            bg_brush = QBrush(QColor(241, 244, 249, 248))
            border_pen = QPen(QColor(215, 222, 232, 230), 1.0)

        painter.fillPath(card_path, bg_brush)
        painter.setPen(border_pen)
        painter.drawPath(card_path)

        # 2. Draw Icon on Left
        icon_x = 13
        icon_y = 13

        if self.toast_type in ("connected", "connect"):
            icon_color = QColor(22, 163, 74)
            pen = QPen(icon_color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            gp = QPainterPath()
            gx, gy = icon_x + 2, icon_y + 4
            gp.moveTo(gx + 4, gy + 7)
            gp.quadTo(gx + 12, gy + 3, gx + 20, gy + 7)
            gp.quadTo(gx + 24, gy + 13, gx + 21.5, gy + 20)
            gp.quadTo(gx + 18, gy + 19, gx + 15.5, gy + 15)
            gp.quadTo(gx + 12, gy + 16.5, gx + 8.5, gy + 15)
            gp.quadTo(gx + 6, gy + 19, gx + 2.5, gy + 20)
            gp.quadTo(gx, gy + 13, gx + 4, gy + 7)
            painter.drawPath(gp)

            painter.setBrush(icon_color)
            painter.drawEllipse(QRectF(gx + 7.5, gy + 10.5, 2.2, 2.2))
            painter.drawEllipse(QRectF(gx + 14.5, gy + 10.5, 2.2, 2.2))

        elif self.toast_type in ("discharging", "unplugged"):
            icon_color = QColor(220, 38, 38)
            pen = QPen(icon_color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            bx, by = icon_x + 3, icon_y + 8
            bw, bh = 22, 14
            painter.drawRoundedRect(QRectF(bx, by, bw, bh), 3.0, 3.0)
            painter.drawLine(bx + bw + 2, by + 4, bx + bw + 2, by + bh - 4)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(icon_color)
            painter.drawRoundedRect(QRectF(bx + 3, by + 3, 7, bh - 6), 1.5, 1.5)

        elif self.toast_type == "charging":
            icon_color = QColor(234, 138, 0)
            pen = QPen(icon_color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            bx, by = icon_x + 3, icon_y + 8
            bw, bh = 22, 14
            painter.drawRoundedRect(QRectF(bx, by, bw, bh), 3.0, 3.0)
            painter.drawLine(bx + bw + 2, by + 4, bx + bw + 2, by + bh - 4)

            painter.setPen(QPen(icon_color, 1.5))
            bolt = QPainterPath()
            lx, ly = bx + 9, by + 2
            bolt.moveTo(lx + 4, ly)
            bolt.lineTo(lx + 1, ly + 5)
            bolt.lineTo(lx + 5, ly + 5)
            bolt.lineTo(lx + 2, ly + 10)
            painter.drawPath(bolt)

        else:  # Disconnected
            icon_color = QColor(100, 116, 139) if is_dark else QColor(148, 163, 184)
            pen = QPen(icon_color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            gp = QPainterPath()
            gx, gy = icon_x + 2, icon_y + 4
            gp.moveTo(gx + 4, gy + 7)
            gp.quadTo(gx + 12, gy + 3, gx + 20, gy + 7)
            gp.quadTo(gx + 24, gy + 13, gx + 21.5, gy + 20)
            gp.quadTo(gx + 18, gy + 19, gx + 15.5, gy + 15)
            gp.quadTo(gx + 12, gy + 16.5, gx + 8.5, gy + 15)
            gp.quadTo(gx + 6, gy + 19, gx + 2.5, gy + 20)
            gp.quadTo(gx, gy + 13, gx + 4, gy + 7)
            painter.drawPath(gp)

            painter.drawLine(gx + 5, gy + 6, gx + 19, gy + 18)

        # 3. Typography
        text_x = icon_x + 36

        font_title = QFont("Segoe UI", 9)
        font_title.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font_title)
        title_color = QColor(241, 245, 249) if is_dark else QColor(15, 23, 42)
        painter.setPen(title_color)
        painter.drawText(text_x, 22, self.title)

        font_sub = QFont("Segoe UI", 8)
        painter.setFont(font_sub)
        sub_color = QColor(148, 163, 184) if is_dark else QColor(71, 85, 105)
        painter.setPen(sub_color)
        painter.drawText(text_x, 38, self.subtitle)


class ToastManager:
    _current_toast = None

    @classmethod
    def show_toast(cls, title: str, subtitle: str, toast_type: str = "connected", theme: str = "light"):
        if cls._current_toast is not None:
            try:
                cls._current_toast.close()
            except Exception:
                pass

        toast = ToastNotification(title=title, subtitle=subtitle, toast_type=toast_type, theme=theme)
        cls._current_toast = toast
        toast.show_animated()
