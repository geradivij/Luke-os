from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame
)
from PyQt5.QtCore import pyqtSignal, QObject, Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QPainter, QPen


class AgentBridge(QObject):
    updated      = pyqtSignal(dict)
    stress_heard = pyqtSignal(str)   # new: stress message signal


class DraggableWidget(QWidget):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._drag_pos = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.window().frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and self._drag_pos:
            self.window().move(e.globalPos() - self._drag_pos)


class ScoreArc(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(84, 84)
        self._score = 0
        self._color = QColor("#A6E3A1")

    def set_score(self, score, color):
        self._score = max(0, min(100, score))
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(10, 10, -10, -10)
        pen = QPen(QColor("#2A2A3E"), 8, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 225 * 16, -270 * 16)
        if self._score > 0:
            span = int(-270 * 16 * self._score / 100)
            pen2 = QPen(self._color, 8, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen2)
            painter.drawArc(rect, 225 * 16, span)
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Courier New", 14, QFont.Bold))
        painter.drawText(rect, Qt.AlignCenter, str(self._score))


class CLRDashboard(QMainWindow):
    def __init__(self, agent):
        super().__init__()
        self.agent = agent
        self.focus_on = False

        self.setWindowTitle("CLR")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.resize(460, 260)
        self.move(20, 20)

        self.bridge = AgentBridge()
        self.bridge.updated.connect(self.handle_update)
        self.bridge.stress_heard.connect(self.show_stress_message)

        self._build_ui()

    def _build_ui(self):
        outer = DraggableWidget()
        outer.setObjectName("outer")
        outer.setStyleSheet("""
            QWidget#outer {
                background-color: #12121E;
                border: 2px solid #89B4FA;
                border-radius: 14px;
            }
        """)
        self.setCentralWidget(outer)

        root = QVBoxLayout(outer)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        # ── Header ──────────────────────────────────────────────────
        header = QHBoxLayout()
        clr = QLabel("CLR")
        clr.setFont(QFont("Courier New", 13, QFont.Bold))
        clr.setStyleSheet("color: #89B4FA; letter-spacing: 4px; background: transparent;")
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #A6E3A1; font-size: 11px; background: transparent;")
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #585B70; border: none; font-size: 13px; }
            QPushButton:hover { color: #F38BA8; }
        """)
        header.addWidget(clr)
        header.addSpacing(6)
        header.addWidget(self.status_dot)
        header.addStretch()
        header.addWidget(self.close_btn)
        root.addLayout(header)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background: #2A2A3E; max-height: 1px;")
        root.addWidget(line)

        # ── Score + Info ─────────────────────────────────────────────
        mid = QHBoxLayout()
        mid.setSpacing(16)
        self.arc = ScoreArc()
        mid.addWidget(self.arc)

        info = QVBoxLayout()
        info.setSpacing(4)
        self.zone_label = QLabel("CALM")
        self.zone_label.setFont(QFont("Courier New", 18, QFont.Bold))
        self.zone_label.setStyleSheet("color: #A6E3A1; letter-spacing: 3px; background: transparent;")
        info.addWidget(self.zone_label)
        self.coach_label = QLabel("All good. Ready when you are.")
        self.coach_label.setWordWrap(True)
        self.coach_label.setFont(QFont("Segoe UI", 10))
        self.coach_label.setStyleSheet("color: #CDD6F4; background: transparent;")
        info.addWidget(self.coach_label)
        self.signal_label = QLabel("sw:0  bs:0  idle:0s  eye:–")
        self.signal_label.setFont(QFont("Courier New", 8))
        self.signal_label.setStyleSheet("color: #45475A; background: transparent;")
        info.addWidget(self.signal_label)
        mid.addLayout(info)
        root.addLayout(mid)

        # ── Stress message banner (hidden by default) ─────────────────
        self.stress_banner = QLabel("")
        self.stress_banner.setWordWrap(True)
        self.stress_banner.setAlignment(Qt.AlignCenter)
        self.stress_banner.setFont(QFont("Segoe UI", 10))
        self.stress_banner.setStyleSheet("""
            background: rgba(243,139,168,0.15);
            color: #F38BA8;
            border: 1px solid rgba(243,139,168,0.4);
            border-radius: 8px;
            padding: 6px 10px;
        """)
        self.stress_banner.hide()
        root.addWidget(self.stress_banner)

        # ── Focus button ─────────────────────────────────────────────
        self.focus_btn = QPushButton("▶   START FOCUS SESSION")
        self.focus_btn.clicked.connect(self.toggle_focus)
        self.focus_btn.setFont(QFont("Courier New", 10, QFont.Bold))
        self.focus_btn.setFixedHeight(40)
        self.focus_btn.setCursor(Qt.PointingHandCursor)
        self._set_btn_idle()
        root.addWidget(self.focus_btn)

        # ── Log strip ────────────────────────────────────────────────
        self.log_label = QLabel("")
        self.log_label.setFont(QFont("Courier New", 8))
        self.log_label.setStyleSheet("color: #585B70; background: transparent;")
        root.addWidget(self.log_label)

    def _set_btn_idle(self):
        self.focus_btn.setStyleSheet("""
            QPushButton {
                background: #1E1E2E; color: #89B4FA;
                border: 1px solid #89B4FA; border-radius: 8px;
                padding: 6px 14px; letter-spacing: 1px;
            }
            QPushButton:hover { background: #2A2A3E; }
        """)

    def _set_btn_active(self):
        self.focus_btn.setStyleSheet("""
            QPushButton {
                background: #1A2E1A; color: #A6E3A1;
                border: 1px solid #A6E3A1; border-radius: 8px;
                padding: 6px 14px; letter-spacing: 1px;
            }
            QPushButton:hover { background: #1F3A1F; }
        """)

    def update_from_agent(self, data: dict):
        self.bridge.updated.emit(data)

    def notify_stress(self, message: str):
        """Called from agent thread when stress voice is detected."""
        self.bridge.stress_heard.emit(message)

    def show_stress_message(self, message: str):
        """Shows gentle message in UI — runs on UI thread."""
        self.stress_banner.setText(f"💬 {message}")
        self.stress_banner.show()
        # auto-hide after 12 seconds
        QTimer.singleShot(12000, self.stress_banner.hide)
        # also resize to fit
        self.adjustSize()

    def handle_update(self, data: dict):
        score   = data.get("score", 0)
        zone    = data.get("zone", "NORMAL")
        signals = data.get("signals", {})
        log     = data.get("log")

        ZONE_CFG = {
            "RAGE":     ("#F38BA8", "OVERLOADED",  "Distractions paused. Breathe."),
            "OVERLOAD": ("#FAB387", "HIGH LOAD",   "Muting noise. Stay in flow."),
            "ELEVATED": ("#F9E2AF", "FOCUSED+",    "Load rising — watching you."),
            "NORMAL":   ("#A6E3A1", "CALM",        "All good. Ready when you are."),
        }
        color, state_text, coach = ZONE_CFG.get(zone, ZONE_CFG["NORMAL"])

        if signals.get("hand_on_face") or signals.get("hand_on_head"):
            coach = "Hand on your face/head — you okay? Take a breath 🌿"
            color = "#F38BA8" if zone in ("NORMAL", "ELEVATED") else color
        elif zone == "NORMAL" and signals.get("on_call") and signals.get("call_minutes", 0) >= 1:
            coach = "Long call — ready to get back?"

        self.arc.set_score(int(score), color)
        self.zone_label.setText(state_text)
        self.zone_label.setStyleSheet(f"color: {color}; letter-spacing: 3px; background: transparent;")
        self.coach_label.setText(coach)
        self.status_dot.setStyleSheet(f"color: {color}; font-size: 11px; background: transparent;")
        self.centralWidget().setStyleSheet(f"""
            QWidget#outer {{
                background-color: #12121E;
                border: 2px solid {color};
                border-radius: 14px;
            }}
        """)

        sw  = signals.get("app_switches_30s", 0)
        bs  = signals.get("backspace_bursts", 0)
        id_ = signals.get("idle_secs", 0)
        ey  = signals.get("eye_state", "?")
        hof = "^^" if signals.get("hand_on_face") else "·"
        hoh = ">>" if signals.get("hand_on_head") else "·"
        app = (signals.get("active_app") or "")[:22]
        self.signal_label.setText(
            f"sw:{sw}  bs:{bs}  idle:{id_}s  eye:{ey}  face:{hof}  head:{hoh}  {app}"
        )

        if log:
            self.log_label.setText(f"⚡ {log}")

    def toggle_focus(self):
        self.focus_on = not self.focus_on
        if self.focus_on:
            self.focus_btn.setText("■   FOCUS SESSION ACTIVE")
            self._set_btn_active()
        else:
            self.focus_btn.setText("▶   START FOCUS SESSION")
            self._set_btn_idle()
            self.coach_label.setText("All good. Ready when you are.")
        if self.agent:
            self.agent.set_focus_mode(self.focus_on)