# main.py
import sys, time, threading
from PyQt5.QtWidgets import QApplication
from vision_pipeline import VisionPipeline
from agent import CLRAgent
from dashboard import CLRDashboard


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    vision = VisionPipeline()
    print("[MAIN] Vision pipeline started")

    # Create dashboard first, then agent with dashboard ref
    agent = CLRAgent(vision_pipeline=vision)
    dashboard = CLRDashboard(agent=agent)

    # Wire everything together
    agent.ui_callback = dashboard.update_from_agent
    agent.dashboard   = dashboard   # for stress banner

    def vision_feed():
        while True:
            agent.set_vision_state(vision.get_state())
            time.sleep(2)
    threading.Thread(target=vision_feed, daemon=True).start()

    # Voice listener
    def start_listener():
        try:
            from voice_input import VoiceListener
            listener = VoiceListener(on_stress_detected=agent.on_stress_detected)
            listener.start()
            print("[MAIN] Voice listener started — say 'I'm so stressed' to trigger")
        except Exception as e:
            print(f"[MAIN] Voice listener unavailable: {e}")
    threading.Thread(target=start_listener, daemon=True).start()

    agent.start()
    dashboard.show()

    def greet():
        time.sleep(1.5)
        try:
            from voice_output import speak_text
            speak_text("CLR is running. Press focus when you're ready and I'll protect your attention.")
        except Exception:
            pass
    threading.Thread(target=greet, daemon=True).start()

    print("[MAIN] CLR running.")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()