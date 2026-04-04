# action_executor.py

import pygetwindow as gw
from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QApplication, QPushButton
)
from PyQt5.QtCore import Qt, QTimer

DISTRACTION_KEYWORDS = [
    "slack", "discord", "whatsapp", "chrome", "edge", "firefox",
    "youtube", "teams", "zoom", "telegram", "instagram", "twitter",
]


def hide_distraction_apps():
    for w in gw.getAllWindows():
        title = (w.title or "").lower()
        if any(k in title for k in DISTRACTION_KEYWORDS):
            print(f"[EXECUTOR] Minimizing: {title}")
            try:
                w.minimize()
            except Exception as e:
                print(f"[EXECUTOR] error: {e}")


def _qt(func):
    if QApplication.instance():
        QTimer.singleShot(0, func)


def show_break_overlay(duration_secs=120, message="Short reset", submessage="", color="#89B4FA"):
    def _show():
        w = QWidget()
        w.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        w.setStyleSheet("background-color: rgba(10,10,20,245);")
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(14)

        title = QLabel(message)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"color: {color}; font-size: 26px; font-weight: bold; font-family: 'Courier New';"
        )
        layout.addWidget(title)

        if submessage:
            sub = QLabel(submessage)
            sub.setAlignment(Qt.AlignCenter)
            sub.setStyleSheet("color: #585B70; font-size: 14px; font-family: 'Courier New';")
            layout.addWidget(sub)

        countdown = QLabel(f"{duration_secs}s")
        countdown.setAlignment(Qt.AlignCenter)
        countdown.setStyleSheet(
            f"color: {color}; font-size: 52px; font-weight: bold; font-family: 'Courier New';"
        )
        layout.addWidget(countdown)

        btn = QPushButton("I'M BACK")
        btn.clicked.connect(w.close)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(137,180,250,0.12); color: {color};
                border: 1px solid {color}44; border-radius: 8px;
                padding: 8px 28px; font-family: 'Courier New';
                font-size: 12px; letter-spacing: 2px;
            }}
            QPushButton:hover {{ background: rgba(137,180,250,0.22); }}
        """)
        layout.addWidget(btn, alignment=Qt.AlignCenter)

        w.showFullScreen()

        remaining = [duration_secs]
        def tick():
            remaining[0] -= 1
            if remaining[0] <= 0:
                w.close()
            else:
                countdown.setText(f"{remaining[0]}s")
        timer = QTimer(w)
        timer.timeout.connect(tick)
        timer.start(1000)

    _qt(_show)


def show_nudge_overlay(message="Back to your project?"):
    def _show():
        w = QWidget()
        w.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        w.setStyleSheet("""
            background: rgba(17,17,27,230);
            border: 1px solid rgba(249,226,175,0.35);
            border-radius: 12px;
        """)
        w.resize(380, 64)
        screen = QApplication.primaryScreen().availableGeometry()
        w.move(screen.width() - 410, 50)

        from PyQt5.QtWidgets import QHBoxLayout
        layout = QHBoxLayout(w)
        layout.setContentsMargins(16, 0, 16, 0)
        icon = QLabel("💡")
        icon.setStyleSheet("font-size: 18px;")
        label = QLabel(message)
        label.setStyleSheet("color: #F9E2AF; font-size: 13px; font-family: 'Courier New';")
        layout.addWidget(icon)
        layout.addWidget(label)

        w.show()
        QTimer.singleShot(7000, w.close)
    _qt(_show)


def show_breathing_overlay(vision_pipeline=None):
    def _show():
        w = QWidget()
        w.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        w.setStyleSheet("background-color: rgba(10,12,20,245);")
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(16)

        emoji = QLabel("🌿")
        emoji.setAlignment(Qt.AlignCenter)
        emoji.setStyleSheet("font-size: 52px;")
        layout.addWidget(emoji)

        msg = QLabel("Take a slow breath.")
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet(
            "color: #A6E3A1; font-size: 24px; font-weight: bold; font-family: 'Courier New';"
        )
        layout.addWidget(msg)

        sub = QLabel("Everything's been closed. Just you and your breath.")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color: #585B70; font-size: 13px; font-family: 'Courier New';")
        layout.addWidget(sub)

        status = QLabel("")
        status.setAlignment(Qt.AlignCenter)
        status.setStyleSheet("color: #89B4FA; font-size: 13px; font-family: 'Courier New';")
        layout.addWidget(status)

        btn = QPushButton("I'M OKAY")
        btn.clicked.connect(w.close)
        btn.setStyleSheet("""
            QPushButton {
                background: rgba(166,227,161,0.12); color: #A6E3A1;
                border: 1px solid rgba(166,227,161,0.35); border-radius: 8px;
                padding: 8px 28px; font-family: 'Courier New';
                font-size: 12px; letter-spacing: 2px;
            }
            QPushButton:hover { background: rgba(166,227,161,0.22); }
        """)
        layout.addWidget(btn, alignment=Qt.AlignCenter)
        w.showFullScreen()

        def check_face():
            if vision_pipeline:
                vs = vision_pipeline.get_state()
                mouth_open = vs.get("mouth_open", False)
                stressed   = vs.get("stressed_face", False)
                try:
                    from voice_output import speak_breathing_still_tense, speak_breathing_relaxed
                    if stressed and not mouth_open:
                        status.setText("You still look a little tense — no rush.")
                        speak_breathing_still_tense()
                    else:
                        status.setText("You're looking better. Nice.")
                        speak_breathing_relaxed()
                except Exception:
                    pass

        QTimer.singleShot(8000, check_face)
        QTimer.singleShot(45000, w.close)

    _qt(_show)


def execute_action(action: str, vision_pipeline=None):
    print(f"[EXECUTOR] Action: {action}")
    a = (action or "").strip().lower()

    try:
        from voice_output import (
            speak_rage, speak_overload, speak_enforce_break,
            speak_nudge, speak_stress_response
        )
    except Exception:
        speak_rage = speak_overload = speak_enforce_break = speak_nudge = speak_stress_response = lambda: None

    if a == "hide_chat_and_focus_work":
        hide_distraction_apps()
        speak_overload()
        show_break_overlay(60, "Chats closed. 60-second reset.", "Close your eyes. Take a breath.", color="#FAB387")

    elif a == "hide_slack_and_break":
        hide_distraction_apps()
        speak_overload()
        show_break_overlay(60, "Slack closed. Quick reset.", "Step back for a moment.", color="#FAB387")

    elif a == "rage_break":
        hide_distraction_apps()
        speak_rage()
        show_break_overlay(300, "OVERLOADED", "Distractions off. Five-minute reset.", color="#F38BA8")

    elif a == "enforce_break":
        speak_enforce_break()
        show_break_overlay(180, "Three-minute break.", "Step away. Look at something far away.", color="#89B4FA")

    elif a in ("soft_nudge", "nudge"):
        speak_nudge()
        show_nudge_overlay("Long call — ready to get back to deep work?")

    elif a == "stress_voice":
        hide_distraction_apps()
        speak_stress_response()
        show_breathing_overlay(vision_pipeline=vision_pipeline)

    else:
        print(f"[EXECUTOR] No-op: {action}")