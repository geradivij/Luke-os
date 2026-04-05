import math
import re
import threading

from PyQt5.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QRect,
    QRectF,
    Qt,
    QPropertyAnimation,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt5.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt5.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

P = {
    "bg": "#090b13",
    "panel": "rgba(13, 18, 29, 232)",
    "panel_alt": "rgba(18, 24, 38, 220)",
    "soft": "rgba(255,255,255,0.06)",
    "soft_2": "rgba(255,255,255,0.11)",
    "border": "rgba(255,255,255,0.10)",
    "border_strong": "rgba(255,255,255,0.20)",
    "text": "#f4f7fb",
    "muted": "#97a3b6",
    "dim": "#5e6b82",
    "blue": "#7dd3fc",
    "cyan": "#67e8f9",
    "mint": "#86efac",
    "yellow": "#facc15",
    "orange": "#fb923c",
    "red": "#fb7185",
    "violet": "#7c93ff",
    "ink": "#0a1020",
}

ZONE_CFG = {
    "RAGE": {"color": P["red"], "title": "Critical Load", "subtitle": "Hard stop. Break the loop and reset before continuing."},
    "OVERLOAD": {"color": P["orange"], "title": "High Load", "subtitle": "Noise is climbing. Cut switching and simplify the next move."},
    "ELEVATED": {"color": P["yellow"], "title": "Elevated", "subtitle": "Attention is drifting. Tighten scope and stay in one lane."},
    "NORMAL": {"color": P["mint"], "title": "Stable", "subtitle": "System is clear. Keep momentum while the signal is clean."},
}


def clean_text(text: str) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2026", "...")
    text = text.encode("ascii", "ignore").decode()
    text = re.sub(r"\s+", " ", text).strip()
    return text


class AgentBridge(QObject):
    updated = pyqtSignal(dict)
    stress_heard = pyqtSignal(str)


class FrostFrame(QFrame):
    def __init__(self, radius=24, panel=False, parent=None):
        super().__init__(parent)
        self.radius = radius
        self.panel = panel
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(self.rect().adjusted(1, 1, -1, -1))
        path = QPainterPath()
        path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(), self.radius, self.radius)

        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        if self.panel:
            gradient.setColorAt(0.0, QColor(22, 28, 44, 240))
            gradient.setColorAt(0.55, QColor(11, 16, 29, 238))
            gradient.setColorAt(1.0, QColor(8, 12, 22, 244))
        else:
            gradient.setColorAt(0.0, QColor(24, 31, 48, 232))
            gradient.setColorAt(1.0, QColor(10, 15, 26, 232))

        painter.fillPath(path, gradient)
        painter.setPen(QPen(QColor(255, 255, 255, 28), 1.2))
        painter.drawPath(path)


class DragSurface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_offset = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.window().frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_offset is not None:
            self.window().move(event.globalPos() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class AvatarOrb(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(104, 104)
        self._zone = "NORMAL"
        self._pulse = 0.0
        self._eye_shift = 0.0
        self._blink = 0.0
        self._phase = 0.0
        self._dragging = False
        self._press_global = None
        self._drag_offset = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._start_blink)
        self.blink_timer.start(2800)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 16)
        shadow.setColor(QColor(0, 0, 0, 130))
        self.setGraphicsEffect(shadow)

    def set_zone(self, zone: str):
        self._zone = zone if zone in ZONE_CFG else "NORMAL"
        self.update()

    def _start_blink(self):
        self._blink = 1.0

    def _tick(self):
        self._phase += 0.08
        self._pulse = (math.sin(self._phase) + 1.0) * 0.5
        self._eye_shift = math.sin(self._phase * 0.37) * 2.8
        if self._blink > 0:
            self._blink = max(0.0, self._blink - 0.16)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self._press_global = event.globalPos()
            self._drag_offset = event.globalPos() - self.window().frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_offset is not None:
            delta = event.globalPos() - self._press_global
            if delta.manhattanLength() > 6:
                self._dragging = True
                self.window().move(event.globalPos() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if not self._dragging:
            self.clicked.emit()
        self._dragging = False
        self._press_global = None
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event):
        zone_color = QColor(ZONE_CFG.get(self._zone, ZONE_CFG["NORMAL"])["color"])

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        center = self.rect().center()
        aura = QRadialGradient(center, 50)
        aura.setColorAt(0.0, QColor(zone_color.red(), zone_color.green(), zone_color.blue(), 70))
        aura.setColorAt(0.6, QColor(zone_color.red(), zone_color.green(), zone_color.blue(), 22))
        aura.setColorAt(1.0, QColor(zone_color.red(), zone_color.green(), zone_color.blue(), 0))
        painter.setBrush(aura)
        painter.drawEllipse(self.rect().adjusted(2, 2, -2, -2))

        shell_rect = self.rect().adjusted(11, 11, -11, -11)
        shell = QRadialGradient(shell_rect.center() + QPoint(-8, -10), shell_rect.width() * 0.7)
        shell.setColorAt(0.0, QColor(161, 221, 255))
        shell.setColorAt(0.55, QColor(92, 140, 255))
        shell.setColorAt(1.0, QColor(29, 47, 97))
        painter.setBrush(shell)
        painter.drawEllipse(shell_rect)

        ear_left = QRectF(shell_rect.left() + 12, shell_rect.top() - 4, 20, 34)
        ear_right = QRectF(shell_rect.right() - 32, shell_rect.top() - 4, 20, 34)
        for ear_rect, tilt in ((ear_left, -8), (ear_right, 8)):
            ear_grad = QLinearGradient(ear_rect.topLeft(), ear_rect.bottomRight())
            ear_grad.setColorAt(0.0, QColor(210, 236, 255, 240))
            ear_grad.setColorAt(0.55, QColor(130, 180, 255, 230))
            ear_grad.setColorAt(1.0, QColor(68, 96, 194, 228))
            painter.setBrush(ear_grad)
            painter.setPen(QPen(QColor(255, 255, 255, 36), 1.0))
            painter.save()
            painter.translate(ear_rect.center())
            painter.rotate(tilt)
            painter.drawRoundedRect(QRectF(-ear_rect.width() / 2, -ear_rect.height() / 2, ear_rect.width(), ear_rect.height()), 10, 10)
            painter.setBrush(QColor(255, 216, 236, 170))
            painter.drawRoundedRect(QRectF(-5, -ear_rect.height() / 2 + 5, 10, ear_rect.height() - 10), 5, 5)
            painter.restore()

        glass_rect = shell_rect.adjusted(8, 12, -8, -8)
        glass = QRadialGradient(glass_rect.center() + QPoint(-3, -12), glass_rect.width() * 0.8)
        glass.setColorAt(0.0, QColor(255, 255, 255, 240))
        glass.setColorAt(0.34, QColor(201, 234, 255, 238))
        glass.setColorAt(0.72, QColor(122, 168, 255, 232))
        glass.setColorAt(1.0, QColor(71, 95, 194, 232))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glass)
        painter.drawEllipse(glass_rect)

        glow_y = int(self._pulse * 3.5)
        painter.setBrush(QColor(255, 255, 255, 48))
        painter.drawEllipse(glass_rect.adjusted(12, 12 + glow_y, -12, -28 + glow_y))

        cheek_color = QColor(255, 206, 225, 115)
        painter.setBrush(cheek_color)
        painter.drawEllipse(QRectF(glass_rect.left() + 12, glass_rect.center().y() + 4, 14, 9))
        painter.drawEllipse(QRectF(glass_rect.right() - 26, glass_rect.center().y() + 4, 14, 9))

        eye_y = glass_rect.center().y() - 1
        blink_height = max(3, int(11 * self._blink))
        painter.setBrush(QColor(7, 16, 42))
        left_eye = QRect(glass_rect.center().x() - 22 + int(self._eye_shift), eye_y - blink_height // 2, 10, blink_height)
        right_eye = QRect(glass_rect.center().x() + 11 + int(self._eye_shift), eye_y - blink_height // 2, 10, blink_height)
        radius = 4 if blink_height > 4 else 2
        painter.drawRoundedRect(left_eye, radius, radius)
        painter.drawRoundedRect(right_eye, radius, radius)

        painter.setBrush(QColor(255, 174, 196, 210))
        painter.setPen(Qt.NoPen)
        nose = QPainterPath()
        nose.moveTo(glass_rect.center().x(), glass_rect.center().y() + 10)
        nose.lineTo(glass_rect.center().x() - 5, glass_rect.center().y() + 16)
        nose.lineTo(glass_rect.center().x() + 5, glass_rect.center().y() + 16)
        nose.closeSubpath()
        painter.drawPath(nose)

        painter.setPen(QPen(QColor(10, 24, 66, 180), 1.4))
        painter.drawLine(glass_rect.center().x(), glass_rect.center().y() + 16, glass_rect.center().x(), glass_rect.center().y() + 21)
        painter.drawArc(glass_rect.center().x() - 12, glass_rect.center().y() + 15, 12, 10, 235 * 16, 130 * 16)
        painter.drawArc(glass_rect.center().x(), glass_rect.center().y() + 15, 12, 10, 175 * 16, 130 * 16)

        status_rect = QRect(self.width() - 28, self.height() - 28, 12, 12)
        painter.setBrush(zone_color)
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1.2))
        painter.drawEllipse(status_rect)


class ScoreRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(184, 184)
        self._display_score = 0.0
        self._target_color = QColor(P["mint"])

        self.score_anim = QVariantAnimation(self)
        self.score_anim.setDuration(700)
        self.score_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.score_anim.valueChanged.connect(self._apply_score)

    def _apply_score(self, value):
        self._display_score = float(value)
        self.update()

    def set_score(self, score: int, color: str):
        score = max(0, min(100, int(score)))
        self._target_color = QColor(color)
        self.score_anim.stop()
        self.score_anim.setStartValue(self._display_score)
        self.score_anim.setEndValue(float(score))
        self.score_anim.start()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(16, 16, -16, -16)
        halo = QRadialGradient(rect.center(), rect.width() * 0.62)
        halo.setColorAt(0.0, QColor(self._target_color.red(), self._target_color.green(), self._target_color.blue(), 55))
        halo.setColorAt(1.0, QColor(self._target_color.red(), self._target_color.green(), self._target_color.blue(), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(rect.adjusted(-12, -12, 12, 12))

        track_pen = QPen(QColor(255, 255, 255, 24), 14, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 210 * 16, -300 * 16)

        arc_pen = QPen(self._target_color, 14, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(arc_pen)
        span = int(-300 * 16 * (self._display_score / 100.0))
        painter.drawArc(rect, 210 * 16, span)

        inner = rect.adjusted(24, 24, -24, -24)
        fill = QRadialGradient(inner.center() + QPoint(-8, -12), inner.width() * 0.78)
        fill.setColorAt(0.0, QColor(28, 39, 61, 246))
        fill.setColorAt(1.0, QColor(11, 17, 29, 246))
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill)
        painter.drawEllipse(inner)

        painter.setPen(QColor(P["text"]))
        painter.setFont(QFont("Segoe UI Variable", 30, QFont.Bold))
        painter.drawText(inner, Qt.AlignCenter, str(int(round(self._display_score))))

        label_rect = inner.adjusted(0, 52, 0, 0)
        painter.setPen(QColor(P["dim"]))
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.drawText(label_rect, Qt.AlignHCenter | Qt.AlignTop, "LOAD SCORE")


class SignalTile(QFrame):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._label_text = label.upper()
        self._build()
        self.set_value("-")

    def _build(self):
        self.setObjectName("signalTile")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        self.label = QLabel(self._label_text)
        self.label.setStyleSheet(f"color: {P['dim']}; font-size: 14px; font-weight: 700; letter-spacing: 0.14em;")

        self.value = QLabel("-")
        self.value.setStyleSheet(f"color: {P['text']}; font-size: 25px; font-weight: 700;")

        layout.addWidget(self.label)
        layout.addWidget(self.value)
        self._set_background(False)

    def _set_background(self, alert: bool):
        border = "rgba(251,113,133,0.60)" if alert else P["border"]
        bg = "rgba(251,113,133,0.10)" if alert else P["soft"]
        value = P["red"] if alert else P["text"]
        self.setStyleSheet(
            f"""
            QFrame#signalTile {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 18px;
            }}
            """
        )
        self.value.setStyleSheet(f"color: {value}; font-size: 25px; font-weight: 700;")

    def set_value(self, text, alert=False):
        self.value.setText(clean_text(text) or "-")
        self._set_background(alert)


class MemoryTab(QWidget):
    _response_ready = pyqtSignal(str)
    _status_ready = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._agents_started = False
        self._memory = None
        self._task_agent = None
        self._status_timer = None
        self._build_ui()
        self._response_ready.connect(self._show_response)
        self._status_ready.connect(self._update_status_label)
        QTimer.singleShot(800, self._ensure_agents)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        self.status_label = QLabel("Starting memory agents")
        self.status_label.setStyleSheet(
            f"""
            background: rgba(125, 211, 252, 0.10);
            color: {P['blue']};
            border: 1px solid rgba(125, 211, 252, 0.22);
            border-radius: 16px;
            padding: 12px 16px;
            font-size: 16px;
            font-weight: 600;
            """
        )
        layout.addWidget(self.status_label)

        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(False)
        self.chat_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.chat_display.setStyleSheet(
            f"""
            QTextBrowser {{
                background: rgba(255,255,255,0.03);
                color: {P['text']};
                border: 1px solid {P['border']};
                border-radius: 28px;
                padding: 24px;
                font-size: 19px;
                line-height: 1.65;
            }}
            QScrollBar:vertical {{
                width: 5px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255,255,255,0.16);
                border-radius: 3px;
            }}
            """
        )
        layout.addWidget(self.chat_display)
        self.chat_display.append(self._bubble_html("Luke", "Memory is live here. Ask what you were doing, who you talked to, or what links you opened.", agent=True))

        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)
        for text in ("What was I doing at 2pm?", "Show pending tasks", "What links did I open today?"):
            btn = QPushButton(text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, value=text: self._prefill(value))
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background: {P['soft']};
                    color: {P['muted']};
                    border: 1px solid {P['border']};
                    border-radius: 18px;
                    padding: 11px 15px;
                    font-size: 16px;
                    text-align: left;
                }}
                QPushButton:hover {{
                    color: {P['text']};
                    border-color: {P['border_strong']};
                }}
                """
            )
            chips_row.addWidget(btn)
        layout.addLayout(chips_row)

        row = QHBoxLayout()
        row.setSpacing(10)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask Luke about your screen history")
        self.input_field.setFixedHeight(58)
        self.input_field.setStyleSheet(
            f"""
            QLineEdit {{
                background: rgba(255,255,255,0.05);
                color: {P['text']};
                border: 1px solid {P['border']};
                border-radius: 20px;
                padding: 0 20px;
                font-size: 19px;
            }}
            QLineEdit:focus {{
                border-color: rgba(125,211,252,0.45);
            }}
            """
        )
        self.input_field.returnPressed.connect(self._send)

        self.send_btn = QPushButton("Send")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setFixedSize(112, 58)
        self.send_btn.clicked.connect(self._send)
        self.send_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {P['blue']}, stop:1 {P['violet']});
                color: {P['ink']};
                border: none;
                border-radius: 20px;
                font-size: 17px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: {P['blue']};
            }}
            QPushButton:disabled {{
                background: rgba(255,255,255,0.12);
                color: {P['dim']};
            }}
            """
        )

        row.addWidget(self.input_field)
        row.addWidget(self.send_btn)
        layout.addLayout(row)

    def _bubble_html(self, speaker: str, text: str, agent=False) -> str:
        speaker = clean_text(speaker)
        text = clean_text(text)
        bg = "rgba(125,211,252,0.11)" if agent else "rgba(124,147,255,0.20)"
        border = "rgba(125,211,252,0.24)" if agent else "rgba(124,147,255,0.30)"
        name = P["blue"] if agent else P["text"]
        align = "left" if agent else "right"
        return (
            f"<div style='text-align:{align}; margin: 8px 0;'>"
            f"<div style='display:inline-block; max-width: 88%; background:{bg}; border:1px solid {border};"
            f" border-radius:22px; padding:16px 18px;'>"
            f"<div style='font-size:15px; font-weight:700; color:{name}; letter-spacing:0.08em; text-transform:uppercase; margin-bottom:8px;'>{speaker}</div>"
            f"<div style='font-size:19px; color:{P['text']};'>{text}</div>"
            f"</div></div>"
        )

    def _prefill(self, text: str):
        self.input_field.setText(clean_text(text))
        self.input_field.setFocus()

    def _ensure_agents(self):
        if self._agents_started:
            return
        try:
            from superluke import _start_writer, CategoryTracker, MemoryAgent, SummaryAgent, TaskAgent, screenshot_loop

            _start_writer()
            self._memory = MemoryAgent()
            summary = SummaryAgent(self._memory)
            self._task_agent = TaskAgent()
            cat_tracker = CategoryTracker()

            prod_tracker = None
            try:
                from productivity import DeviceTracker

                prod_tracker = DeviceTracker()
                prod_tracker.start()
            except Exception:
                pass

            threading.Thread(target=screenshot_loop, args=(self._memory, self._task_agent, prod_tracker, cat_tracker), daemon=True, name="superluke-screenshot").start()
            threading.Thread(target=summary.run_loop, daemon=True, name="superluke-summary").start()

            self._agents_started = True
            self._status_ready.emit("Memory active")
            self.status_label.setStyleSheet(
                f"""
                background: rgba(134,239,172,0.10);
                color: {P['mint']};
                border: 1px solid rgba(134,239,172,0.22);
                border-radius: 14px;
                padding: 8px 12px;
                font-size: 12px;
                font-weight: 600;
                """
            )
            self._status_timer = QTimer(self)
            self._status_timer.timeout.connect(self._poll_status)
            self._status_timer.start(10_000)
        except Exception as e:
            self._status_ready.emit(f"Memory unavailable: {clean_text(e)}")
            self.status_label.setStyleSheet(
                f"""
                background: rgba(251,113,133,0.10);
                color: {P['red']};
                border: 1px solid rgba(251,113,133,0.22);
                border-radius: 14px;
                padding: 8px 12px;
                font-size: 12px;
                font-weight: 600;
                """
            )

    def _poll_status(self):
        if not self._agents_started:
            return

        def _read():
            try:
                from superluke import SUMMARIES_FILE, _buffer_lock, _raw_buffer, load_json

                with _buffer_lock:
                    buf = len(_raw_buffer)
                sums = load_json(SUMMARIES_FILE, [])
                tasks = self._task_agent.list_tasks() if self._task_agent else []
                self._status_ready.emit(f"Live memory | buffer {buf} | windows {len(sums)} | tasks {len(tasks)}")
            except Exception:
                pass

        threading.Thread(target=_read, daemon=True).start()

    def _update_status_label(self, text: str):
        self.status_label.setText(clean_text(text))

    def _send(self):
        msg = clean_text(self.input_field.text())
        if not msg:
            return
        if not self._memory:
            self.chat_display.append(self._bubble_html("System", "Memory agents are still starting. Wait a moment.", agent=True))
            return

        self.input_field.clear()
        self.chat_display.append(self._bubble_html("You", msg, agent=False))
        self.send_btn.setEnabled(False)
        self.send_btn.setText("...")

        def _ask():
            try:
                response = self._memory.chat(msg)
            except Exception as e:
                response = f"Error: {clean_text(e)}"
            self._response_ready.emit(response)

        threading.Thread(target=_ask, daemon=True).start()

    def _show_response(self, response: str):
        self.chat_display.append(self._bubble_html("Luke", response, agent=True))
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Send")
        self.chat_display.verticalScrollBar().setValue(self.chat_display.verticalScrollBar().maximum())


class CLRDashboard(QMainWindow):
    def __init__(self, agent):
        super().__init__()
        self.agent = agent
        self.focus_on = False
        self.expanded = False
        self.current_zone = "NORMAL"
        self._stress_banner_timer = QTimer(self)
        self._stress_banner_timer.setSingleShot(True)
        self._stress_banner_timer.timeout.connect(self._hide_stress_banner)

        self._collapsed_rect = QRect(28, 28, 128, 128)
        self._expanded_rect = QRect(28, 28, 1180, 900)

        self.setWindowTitle("Luke")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(self._collapsed_rect)

        self.bridge = AgentBridge()
        self.bridge.updated.connect(self.handle_update)
        self.bridge.stress_heard.connect(self.show_stress_message)

        self._build_ui()
        self._build_animations()
        self._sync_expanded_state(False)

    def _build_ui(self):
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(16)
        self.setCentralWidget(root)

        self.avatar_host = QWidget()
        self.avatar_host.setFixedWidth(126)
        avatar_layout = QVBoxLayout(self.avatar_host)
        avatar_layout.setContentsMargins(0, 0, 0, 0)
        avatar_layout.setSpacing(10)
        avatar_layout.addStretch()

        self.avatar = AvatarOrb()
        self.avatar.clicked.connect(self.toggle_panel)

        self.avatar_label = QLabel("Luke")
        self.avatar_label.setAlignment(Qt.AlignCenter)
        self.avatar_label.setStyleSheet(f"color: {P['text']}; font-size: 18px; font-weight: 700; letter-spacing: 0.10em; text-transform: uppercase;")

        self.avatar_caption = QLabel("click to open")
        self.avatar_caption.setAlignment(Qt.AlignCenter)
        self.avatar_caption.setStyleSheet(f"color: {P['dim']}; font-size: 15px;")

        avatar_layout.addWidget(self.avatar, 0, Qt.AlignCenter)
        avatar_layout.addWidget(self.avatar_label)
        avatar_layout.addWidget(self.avatar_caption)
        avatar_layout.addStretch()
        root_layout.addWidget(self.avatar_host, 0, Qt.AlignLeft)

        self.panel_wrap = FrostFrame(radius=30, panel=True)
        root_layout.addWidget(self.panel_wrap, 1)

        shadow = QGraphicsDropShadowEffect(self.panel_wrap)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 22)
        shadow.setColor(QColor(0, 0, 0, 145))
        self.panel_wrap.setGraphicsEffect(shadow)

        panel_layout = QVBoxLayout(self.panel_wrap)
        panel_layout.setContentsMargins(32, 28, 32, 32)
        panel_layout.setSpacing(24)

        self.header = DragSurface()
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(14)

        title_stack = QVBoxLayout()
        title_stack.setContentsMargins(0, 0, 0, 0)
        title_stack.setSpacing(3)
        self.title_label = QLabel("Luke")
        self.title_label.setStyleSheet(f"color: {P['text']}; font-size: 35px; font-weight: 700;")
        self.subtitle_label = QLabel("attention guard and memory desk")
        self.subtitle_label.setStyleSheet(f"color: {P['muted']}; font-size: 19px;")
        title_stack.addWidget(self.title_label)
        title_stack.addWidget(self.subtitle_label)

        header_layout.addLayout(title_stack)
        header_layout.addStretch()

        self.mode_badge = QLabel("Stable")
        self.mode_badge.setAlignment(Qt.AlignCenter)
        self.mode_badge.setFixedHeight(34)
        header_layout.addWidget(self.mode_badge)

        self.collapse_btn = QPushButton("Hide")
        self.collapse_btn.setCursor(Qt.PointingHandCursor)
        self.collapse_btn.clicked.connect(self.toggle_panel)
        self.collapse_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {P['soft']};
                color: {P['text']};
                border: 1px solid {P['border']};
                border-radius: 17px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                border-color: {P['border_strong']};
            }}
            """
        )
        header_layout.addWidget(self.collapse_btn)

        self.close_btn = QPushButton("Quit")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: rgba(251,113,133,0.10);
                color: {P['red']};
                border: 1px solid rgba(251,113,133,0.24);
                border-radius: 17px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: rgba(251,113,133,0.18);
            }}
            """
        )
        header_layout.addWidget(self.close_btn)
        panel_layout.addWidget(self.header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{
                border: none;
                background: transparent;
            }}
            QTabBar::tab {{
                min-width: 170px;
                padding: 16px 24px;
                margin-right: 8px;
                border-radius: 16px;
                background: {P['soft']};
                color: {P['muted']};
                font-size: 16px;
                font-weight: 700;
            }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(125,211,252,0.22), stop:1 rgba(124,147,255,0.20));
                color: {P['text']};
                border: 1px solid rgba(125,211,252,0.20);
            }}
            QTabBar::tab:hover:!selected {{
                color: {P['text']};
            }}
            """
        )
        panel_layout.addWidget(self.tabs, 1)

        self._build_focus_tab()
        self.memory_tab = MemoryTab()
        self.tabs.addTab(self.memory_tab, "Memory")
        self._set_zone_style("NORMAL", 0)

    def _build_focus_tab(self):
        focus_tab = QWidget()
        layout = QVBoxLayout(focus_tab)
        layout.setContentsMargins(0, 18, 0, 0)
        layout.setSpacing(22)

        self.zone_card = FrostFrame(radius=24)
        zone_layout = QHBoxLayout(self.zone_card)
        zone_layout.setContentsMargins(24, 22, 24, 22)
        zone_layout.setSpacing(14)

        self.zone_indicator = QLabel()
        self.zone_indicator.setFixedSize(12, 12)
        self.zone_indicator.setStyleSheet(f"background: {P['mint']}; border-radius: 6px;")

        zone_text_layout = QVBoxLayout()
        zone_text_layout.setContentsMargins(0, 0, 0, 0)
        zone_text_layout.setSpacing(4)

        self.zone_label = QLabel("Stable")
        self.zone_label.setStyleSheet(f"color: {P['text']}; font-size: 29px; font-weight: 700;")

        self.coach_label = QLabel(ZONE_CFG["NORMAL"]["subtitle"])
        self.coach_label.setWordWrap(True)
        self.coach_label.setStyleSheet(f"color: {P['muted']}; font-size: 19px; line-height: 1.5;")

        zone_text_layout.addWidget(self.zone_label)
        zone_text_layout.addWidget(self.coach_label)
        zone_layout.addWidget(self.zone_indicator, 0, Qt.AlignTop)
        zone_layout.addLayout(zone_text_layout, 1)
        layout.addWidget(self.zone_card)

        self.hero_card = FrostFrame(radius=28)
        hero_layout = QHBoxLayout(self.hero_card)
        hero_layout.setContentsMargins(30, 28, 30, 28)
        hero_layout.setSpacing(30)

        self.arc = ScoreRing()
        hero_layout.addWidget(self.arc, 0, Qt.AlignVCenter)

        side = QVBoxLayout()
        side.setSpacing(14)

        block = QVBoxLayout()
        block.setSpacing(4)
        self.hero_title = QLabel("Stay clean")
        self.hero_title.setStyleSheet(f"color: {P['text']}; font-size: 35px; font-weight: 700;")
        self.hero_copy = QLabel("Luke tracks cognitive pressure in real time and steps in when your attention starts leaking.")
        self.hero_copy.setWordWrap(True)
        self.hero_copy.setStyleSheet(f"color: {P['muted']}; font-size: 19px; line-height: 1.55;")
        block.addWidget(self.hero_title)
        block.addWidget(self.hero_copy)

        self.focus_btn = QPushButton("Start focus session")
        self.focus_btn.setCursor(Qt.PointingHandCursor)
        self.focus_btn.setFixedHeight(62)
        self.focus_btn.clicked.connect(self.toggle_focus)
        self.focus_btn.setStyleSheet(self._focus_button_style(active=False))

        self.log_label = QLabel("No interventions yet.")
        self.log_label.setWordWrap(True)
        self.log_label.setStyleSheet(f"color: {P['dim']}; font-size: 16px;")

        side.addLayout(block)
        side.addWidget(self.focus_btn)
        side.addWidget(self.log_label)
        side.addStretch()
        hero_layout.addLayout(side, 1)
        layout.addWidget(self.hero_card)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)

        self._tiles = {
            "switches": SignalTile("Switches"),
            "bursts": SignalTile("Bursts"),
            "idle": SignalTile("Idle"),
            "eye": SignalTile("Eyes"),
            "face": SignalTile("Face"),
            "head": SignalTile("Head"),
        }

        grid.addWidget(self._tiles["switches"], 0, 0)
        grid.addWidget(self._tiles["bursts"], 0, 1)
        grid.addWidget(self._tiles["idle"], 0, 2)
        grid.addWidget(self._tiles["eye"], 1, 0)
        grid.addWidget(self._tiles["face"], 1, 1)
        grid.addWidget(self._tiles["head"], 1, 2)

        self.app_card = SignalTile("Active App")
        self.app_card.value.setStyleSheet(f"color: {P['text']}; font-size: 21px; font-weight: 700;")
        grid.addWidget(self.app_card, 2, 0, 1, 3)
        layout.addLayout(grid)

        self.stress_banner = QLabel("")
        self.stress_banner.hide()
        self.stress_banner.setWordWrap(True)
        self.stress_banner.setStyleSheet(
            f"""
            background: rgba(251,113,133,0.10);
            color: {P['red']};
            border: 1px solid rgba(251,113,133,0.25);
            border-radius: 22px;
            padding: 16px 18px;
            font-size: 18px;
            font-weight: 600;
            """
        )
        layout.addWidget(self.stress_banner)
        layout.addStretch()

        self.tabs.addTab(focus_tab, "Focus")

    def _build_animations(self):
        self.window_anim = QPropertyAnimation(self, b"geometry")
        self.window_anim.setDuration(360)
        self.window_anim.setEasingCurve(QEasingCurve.OutCubic)

        self.panel_width_anim = QPropertyAnimation(self.panel_wrap, b"maximumWidth")
        self.panel_width_anim.setDuration(320)
        self.panel_width_anim.setEasingCurve(QEasingCurve.OutCubic)

    def _sync_expanded_state(self, expanded: bool):
        self.expanded = expanded
        if expanded:
            self.setGeometry(self._expanded_rect)
            self.panel_wrap.setMaximumWidth(self._expanded_rect.width() - self.avatar_host.width() - 28)
            self.panel_wrap.show()
            self.avatar_caption.setText("drag to move")
        else:
            self.setGeometry(self._collapsed_rect)
            self.panel_wrap.setMaximumWidth(0)
            self.panel_wrap.hide()
            self.avatar_caption.setText("click to open")

    def toggle_panel(self):
        start = self.geometry()
        if self.expanded:
            target = QRect(start.x(), start.y(), self._collapsed_rect.width(), self._collapsed_rect.height())
            self.panel_width_anim.stop()
            self.panel_width_anim.setStartValue(max(0, self.panel_wrap.width()))
            self.panel_width_anim.setEndValue(0)
            self.panel_width_anim.start()
            self.window_anim.stop()
            self.window_anim.setStartValue(start)
            self.window_anim.setEndValue(target)
            self.window_anim.start()
            QTimer.singleShot(320, lambda: (not self.expanded) and self.panel_wrap.hide())
            self.expanded = False
            self.avatar_caption.setText("click to open")
        else:
            target = QRect(start.x(), start.y(), self._expanded_rect.width(), self._expanded_rect.height())
            self.panel_wrap.show()
            self.panel_width_anim.stop()
            self.panel_width_anim.setStartValue(0)
            self.panel_width_anim.setEndValue(self._expanded_rect.width() - self.avatar_host.width() - 28)
            self.panel_width_anim.start()
            self.window_anim.stop()
            self.window_anim.setStartValue(start)
            self.window_anim.setEndValue(target)
            self.window_anim.start()
            self.expanded = True
            self.avatar_caption.setText("drag to move")

    def _focus_button_style(self, active: bool):
        if active:
            return (
                f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {P['mint']}, stop:1 {P['cyan']});
                    color: {P['ink']};
                    border: none;
                    border-radius: 18px;
                    font-size: 19px;
                    font-weight: 700;
                }}
                QPushButton:hover {{
                    background: {P['mint']};
                }}
                """
            )
        return (
            f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {P['blue']}, stop:1 {P['violet']});
                    color: {P['ink']};
                    border: none;
                    border-radius: 18px;
                    font-size: 19px;
                    font-weight: 700;
                }}
            QPushButton:hover {{
                background: {P['blue']};
            }}
            """
        )

    def update_from_agent(self, data: dict):
        self.bridge.updated.emit(data)

    def notify_stress(self, message: str):
        self.bridge.stress_heard.emit(message)

    def show_stress_message(self, message: str):
        self.stress_banner.setText(clean_text(message))
        self.stress_banner.show()
        self._stress_banner_timer.start(12_000)
        if not self.expanded:
            self.toggle_panel()
        self.tabs.setCurrentIndex(0)

    def _hide_stress_banner(self):
        self.stress_banner.hide()

    def _set_zone_style(self, zone: str, score: int):
        cfg = ZONE_CFG.get(zone, ZONE_CFG["NORMAL"])
        color = cfg["color"]
        self.current_zone = zone
        self.avatar.set_zone(zone)
        self.arc.set_score(score, color)
        self.zone_label.setText(cfg["title"])
        self.coach_label.setText(cfg["subtitle"])
        self.mode_badge.setText(cfg["title"])
        qcolor = QColor(color)
        self.mode_badge.setStyleSheet(
            f"""
            background: rgba({qcolor.red()}, {qcolor.green()}, {qcolor.blue()}, 0.12);
            color: {color};
            border: 1px solid rgba({qcolor.red()}, {qcolor.green()}, {qcolor.blue()}, 0.25);
            border-radius: 17px;
            padding: 0 14px;
            font-size: 12px;
            font-weight: 700;
            """
        )
        self.zone_indicator.setStyleSheet(f"background: {color}; border-radius: 6px;")
        self.hero_title.setText(cfg["title"])

    def handle_update(self, data: dict):
        score = int(data.get("score", 0))
        zone = data.get("zone", "NORMAL")
        signals = data.get("signals", {}) or {}
        log = clean_text(data.get("log") or "")

        self._set_zone_style(zone, score)

        coach = ZONE_CFG.get(zone, ZONE_CFG["NORMAL"])["subtitle"]
        if signals.get("hand_on_face") or signals.get("hand_on_head"):
            coach = "Physical stress cue detected. Pause, reset your breathing, and reduce pressure."
        elif zone == "NORMAL" and signals.get("on_call") and signals.get("call_minutes", 0) >= 1:
            coach = "Long call in progress. Lock the next task before context slips."
        self.coach_label.setText(clean_text(coach))

        self._tiles["switches"].set_value(str(signals.get("app_switches_30s", 0)), alert=signals.get("app_switches_30s", 0) >= 6)
        self._tiles["bursts"].set_value(str(signals.get("backspace_bursts", 0)), alert=signals.get("backspace_bursts", 0) >= 3)
        self._tiles["idle"].set_value(f"{signals.get('idle_secs', 0)}s", alert=signals.get("idle_secs", 0) >= 60)
        self._tiles["eye"].set_value(clean_text(signals.get("eye_state", "unknown")).title(), alert=signals.get("eye_state") == "closed")
        self._tiles["face"].set_value("Detected" if signals.get("hand_on_face") else "Clear", alert=signals.get("hand_on_face"))
        self._tiles["head"].set_value("Detected" if signals.get("hand_on_head") else "Clear", alert=signals.get("hand_on_head"))
        self.app_card.set_value(clean_text(signals.get("active_app") or "None"), alert=False)

        self.log_label.setText(log or "No interventions yet.")

    def toggle_focus(self):
        self.focus_on = not self.focus_on
        if self.focus_on:
            self.focus_btn.setText("Focus session active")
            self.hero_copy.setText("Luke will step in automatically if stress spikes or the loop starts slipping.")
        else:
            self.focus_btn.setText("Start focus session")
            self.hero_copy.setText("Luke tracks cognitive pressure in real time and steps in when your attention starts leaking.")
        self.focus_btn.setStyleSheet(self._focus_button_style(active=self.focus_on))
        if self.agent:
            self.agent.set_focus_mode(self.focus_on)
