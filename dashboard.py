import threading
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QTabWidget,
    QTextBrowser, QLineEdit
)
from PyQt5.QtCore import pyqtSignal, QObject, Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QPainter, QPen


class AgentBridge(QObject):
    updated      = pyqtSignal(dict)
    stress_heard = pyqtSignal(str)


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


# ── Memory Tab ─────────────────────────────────────────────────────────────────

class MemoryTab(QWidget):
    _response_ready = pyqtSignal(str)
    _status_ready   = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._agents_started = False
        self._memory     = None
        self._task_agent = None
        self._status_timer = None
        self._build_ui()
        self._response_ready.connect(self._show_response)
        self._status_ready.connect(self._update_status_label)
        # boot agents shortly after UI is ready
        QTimer.singleShot(800, self._ensure_agents)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Status bar
        self.status_label = QLabel("● Starting memory agents...")
        self.status_label.setFont(QFont("Courier New", 8))
        self.status_label.setStyleSheet("color: #585B70; background: transparent;")
        layout.addWidget(self.status_label)

        # Chat display
        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(False)
        self.chat_display.setFont(QFont("Segoe UI", 9))
        self.chat_display.setStyleSheet("""
            QTextBrowser {
                background: #0d0d1a;
                color: #CDD6F4;
                border: 1px solid #2A2A3E;
                border-radius: 6px;
                padding: 6px;
            }
        """)
        layout.addWidget(self.chat_display)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask Luke anything about your screen history...")
        self.input_field.setFont(QFont("Segoe UI", 9))
        self.input_field.setFixedHeight(32)
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: #1E1E2E;
                color: #CDD6F4;
                border: 1px solid #2A2A3E;
                border-radius: 6px;
                padding: 4px 8px;
            }
            QLineEdit:focus { border-color: #89B4FA; }
        """)
        self.input_field.returnPressed.connect(self._send)

        self.send_btn = QPushButton("Ask")
        self.send_btn.setFont(QFont("Courier New", 9, QFont.Bold))
        self.send_btn.setFixedSize(52, 32)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(self._send)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background: #1E1E2E; color: #89B4FA;
                border: 1px solid #89B4FA; border-radius: 6px;
            }
            QPushButton:hover { background: #2A2A3E; }
            QPushButton:disabled { color: #45475A; border-color: #2A2A3E; }
        """)

        input_row.addWidget(self.input_field)
        input_row.addWidget(self.send_btn)
        layout.addLayout(input_row)

    def _ensure_agents(self):
        if self._agents_started:
            return
        try:
            from superluke import (
                _start_writer, MemoryAgent, SummaryAgent,
                TaskAgent, CategoryTracker, screenshot_loop
            )
            _start_writer()
            self._memory     = MemoryAgent()
            summary          = SummaryAgent(self._memory)
            self._task_agent = TaskAgent()
            cat_tracker      = CategoryTracker()

            prod_tracker = None
            try:
                from productivity import DeviceTracker
                prod_tracker = DeviceTracker()
                prod_tracker.start()
            except Exception:
                pass

            threading.Thread(
                target=screenshot_loop,
                args=(self._memory, self._task_agent, prod_tracker, cat_tracker),
                daemon=True,
                name="superluke-screenshot",
            ).start()
            threading.Thread(
                target=summary.run_loop,
                daemon=True,
                name="superluke-summary",
            ).start()

            self._agents_started = True
            self._status_ready.emit("● Live — watching screen")
            self.status_label.setStyleSheet("color: #A6E3A1; background: transparent; font-size: 8pt;")

            self._status_timer = QTimer(self)
            self._status_timer.timeout.connect(self._poll_status)
            self._status_timer.start(10_000)

        except Exception as e:
            self._status_ready.emit(f"✗ Memory unavailable: {e}")
            self.status_label.setStyleSheet("color: #F38BA8; background: transparent; font-size: 8pt;")

    def _poll_status(self):
        if not self._agents_started:
            return
        def _read():
            try:
                from superluke import _raw_buffer, _buffer_lock, load_json, SUMMARIES_FILE
                with _buffer_lock:
                    buf = len(_raw_buffer)
                sums  = load_json(SUMMARIES_FILE, [])
                tasks = self._task_agent.list_tasks() if self._task_agent else []
                self._status_ready.emit(
                    f"● Live  buf:{buf}  wins:{len(sums)}  tasks:{len(tasks)}"
                )
            except Exception:
                pass
        threading.Thread(target=_read, daemon=True).start()

    def _update_status_label(self, text: str):
        self.status_label.setText(text)

    def _send(self):
        msg = self.input_field.text().strip()
        if not msg:
            return
        if not self._memory:
            self.chat_display.append(
                "<span style='color:#F38BA8'>Memory agents are still starting up — wait a moment.</span>"
            )
            return
        self.input_field.clear()
        self.chat_display.append(
            f"<p style='margin:4px 0'><span style='color:#89B4FA'><b>You</b></span>&nbsp; {msg}</p>"
        )
        self.send_btn.setEnabled(False)
        self.send_btn.setText("...")

        def _ask():
            try:
                response = self._memory.chat(msg)
            except Exception as e:
                response = f"Error: {e}"
            self._response_ready.emit(response)

        threading.Thread(target=_ask, daemon=True).start()

    def _show_response(self, response: str):
        self.chat_display.append(
            f"<p style='margin:4px 0'><span style='color:#A6E3A1'><b>Luke</b></span>&nbsp; {response}</p>"
        )
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Ask")


# ── Main Dashboard ─────────────────────────────────────────────────────────────

class CLRDashboard(QMainWindow):
    def __init__(self, agent):
        super().__init__()
        self.agent    = agent
        self.focus_on = False

        self.setWindowTitle("CLR")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.resize(460, 360)   # taller than before to fit tab bar without squeezing CLR
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

        # ── Header (shared across all tabs) ────────────────────────────────
        header = QHBoxLayout()
        clr_lbl = QLabel("CLR")
        clr_lbl.setFont(QFont("Courier New", 13, QFont.Bold))
        clr_lbl.setStyleSheet("color: #89B4FA; letter-spacing: 4px; background: transparent;")
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #A6E3A1; font-size: 11px; background: transparent;")
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #585B70; border: none; font-size: 13px; }
            QPushButton:hover { color: #F38BA8; }
        """)
        header.addWidget(clr_lbl)
        header.addSpacing(6)
        header.addWidget(self.status_dot)
        header.addStretch()
        header.addWidget(self.close_btn)
        root.addLayout(header)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background: #2A2A3E; max-height: 1px;")
        root.addWidget(line)

        # ── Tab widget ──────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background: transparent;
            }
            QTabBar::tab {
                background: #1E1E2E;
                color: #585B70;
                border: 1px solid #2A2A3E;
                border-bottom: none;
                border-radius: 4px 4px 0 0;
                padding: 4px 14px;
                font-family: "Courier New";
                font-size: 9pt;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #12121E;
                color: #89B4FA;
                border-color: #89B4FA;
            }
            QTabBar::tab:hover:!selected {
                color: #CDD6F4;
            }
        """)
        root.addWidget(self.tabs)

        # ── Tab 1: CLR ──────────────────────────────────────────────────────
        clr_tab = QWidget()
        clr_tab.setStyleSheet("background: transparent;")
        clr_layout = QVBoxLayout(clr_tab)
        clr_layout.setContentsMargins(0, 8, 0, 0)
        clr_layout.setSpacing(8)

        # Score + Info
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
        clr_layout.addLayout(mid)

        # Stress banner
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
        clr_layout.addWidget(self.stress_banner)

        # Focus button
        self.focus_btn = QPushButton("▶   START FOCUS SESSION")
        self.focus_btn.clicked.connect(self.toggle_focus)
        self.focus_btn.setFont(QFont("Courier New", 10, QFont.Bold))
        self.focus_btn.setFixedHeight(40)
        self.focus_btn.setCursor(Qt.PointingHandCursor)
        self._set_btn_idle()
        clr_layout.addWidget(self.focus_btn)

        # Log strip
        self.log_label = QLabel("")
        self.log_label.setFont(QFont("Courier New", 8))
        self.log_label.setStyleSheet("color: #585B70; background: transparent;")
        clr_layout.addWidget(self.log_label)

        clr_layout.addStretch()
        self.tabs.addTab(clr_tab, "CLR")

        # ── Tab 2: Memory ───────────────────────────────────────────────────
        self.memory_tab = MemoryTab()
        self.tabs.addTab(self.memory_tab, "🧠 Memory")

    # ── CLR styling helpers (unchanged) ────────────────────────────────────────

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

    # ── Public API called from agent thread (unchanged) ────────────────────────

    def update_from_agent(self, data: dict):
        self.bridge.updated.emit(data)

    def notify_stress(self, message: str):
        self.bridge.stress_heard.emit(message)

    def show_stress_message(self, message: str):
        self.stress_banner.setText(f"💬 {message}")
        self.stress_banner.show()
        QTimer.singleShot(12000, self.stress_banner.hide)
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
