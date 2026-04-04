# agent.py
import time
import threading
from signal_collector import SignalCollector
from load_score import LoadScoreEngine
from memory import AgentMemory

STRESS_UI_MESSAGES = [
    "Heard you. Don't give up — you're closer than you think 💙",
    "Hey, it's okay to feel like this. Take a breath.",
    "I heard that. One thing at a time.",
    "Don't give up yet. I'm right here.",
]

class CLRAgent:
    def __init__(self, ui_callback=None, vision_pipeline=None, dashboard=None):
        self.focus_mode = False
        self.auto_focus_enabled = True
        self.collector = SignalCollector()
        self.scorer = LoadScoreEngine()
        self.vision_state = {}
        self.ui_callback = ui_callback
        self.dashboard = dashboard
        self.last_zone = "NORMAL"
        self.vision_pipeline = vision_pipeline
        self.memory = AgentMemory()
        self.cooldown_secs = self.memory.get_adapted_cooldown()
        self.last_intervention = 0
        self._last_hand_voice = 0   # throttle hand voice
        self._hand_was_detected = False  # track state change

        self.action_map = {
            "hide_chat_and_focus_work": "hide_chat_and_focus_work",
            "soft_nudge":               "nudge",
            "enforce_break":            "enforce_break",
            "rage_break":               "rage_break",
            "no_action":                None,
        }

    def set_vision_state(self, vs: dict):
        self.vision_state = vs or {}

    def set_focus_mode(self, enabled: bool):
        self.focus_mode = enabled
        print(f"[AGENT] Focus Mode: {'ON' if enabled else 'OFF'}")
        try:
            from voice_output import speak_focus_on, speak_focus_off, speak_text
            if enabled:
                warning = self.memory.get_peak_hour_warning()
                speak_text(warning) if warning else speak_focus_on()
            else:
                speak_focus_off()
                print("[MEMORY]\n" + self.memory.summary())
        except Exception:
            pass

    def on_stress_detected(self, text: str):
        import random
        print(f"[AGENT] Stress phrase heard: '{text}'")
        message = random.choice(STRESS_UI_MESSAGES)
        if self.dashboard:
            self.dashboard.notify_stress(message)
        try:
            from voice_output import speak_stress_comfort
            speak_stress_comfort()
        except Exception:
            pass
        try:
            from action_executor import show_breathing_overlay
            show_breathing_overlay(vision_pipeline=self.vision_pipeline)
        except Exception as e:
            print(f"[AGENT] breathing overlay error: {e}")

    def maybe_auto_focus(self, score, zone, signals):
        if not self.auto_focus_enabled:
            return
        on_call      = signals.get("on_call", False)
        call_minutes = signals.get("call_minutes", 0)
        stressed     = signals.get("stressed_face", False)
        if on_call and call_minutes >= 2 and stressed and not self.focus_mode:
            self._execute_nudge_only()
            return
        if not self.focus_mode:
            switches = signals.get("app_switches_30s", 0)
            bursts   = signals.get("backspace_bursts", 0)
            if score >= 80 or (switches >= 6 and bursts >= 3):
                self.set_focus_mode(True)

    def _execute_nudge_only(self):
        try:
            from voice_output import speak_nudge
            speak_nudge()
            from action_executor import show_nudge_overlay
            show_nudge_overlay("Long call — ready to get back to deep work?")
        except Exception as e:
            print(f"[AGENT] nudge error: {e}")

    def _get_action(self, zone, signals, score):
        memory_suggestion = self.memory.get_best_action(zone)
        state = {
            "app_switches_30s": signals.get("app_switches_30s", 0),
            "backspace_bursts":  signals.get("backspace_bursts", 0),
            "idle_secs":         signals.get("idle_secs", 0),
            "eye_state":         signals.get("eye_state", "unknown"),
            "load_score":        score,
            "active_app":        signals.get("active_app", "other"),
        }
        try:
            from gemma_decider_local import get_label
            gemma_label = get_label(state)
            print(f"[AGENT] Gemma -> {gemma_label}")
        except Exception as e:
            print(f"[AGENT] Gemma fallback ({e})")
            gemma_label = "rage_break" if zone == "RAGE" else "hide_chat_and_focus_work"

        label = memory_suggestion if (memory_suggestion and memory_suggestion != gemma_label) else gemma_label
        return self.action_map.get(label)

    def _execute(self, action_str):
        if not action_str:
            return
        print(f"[AGENT] Executing: {action_str}")
        try:
            from action_executor import execute_action
            execute_action(action_str, vision_pipeline=self.vision_pipeline)
        except Exception as e:
            print(f"[AGENT] executor error: {e}")

    def _observe_outcome(self, idx, score_before):
        def _check():
            time.sleep(120)
            signals     = self.collector.get_state(self.vision_state)
            result      = self.scorer.compute(signals)
            score_after = result.get("score", 0)
            active      = (signals.get("active_app") or "").lower()
            reopened    = any(k in active for k in ["slack","discord","whatsapp","youtube","twitter"])
            self.memory.observe_outcome(idx, score_after, reopened)
            print(f"[MEMORY] Outcome: {score_before}->{score_after} reopened={reopened}")
            if score_after < score_before - 10 and not reopened:
                try:
                    from voice_output import speak_text
                    speak_text("Good. Your load came down. Nice reset.")
                except Exception:
                    pass
        threading.Thread(target=_check, daemon=True).start()

    def _run_loop(self):
        while True:
            time.sleep(2)
            signals = self.collector.get_state(self.vision_state)
            result  = self.scorer.compute(signals)
            score   = result.get("score", 0)
            zone    = result.get("zone", "NORMAL")

            print(f"[AGENT] Score={score} Zone={zone} App={signals.get('active_app','?')}")

            if self.ui_callback:
                self.ui_callback({"score": score, "zone": zone, "signals": signals, "log": None})

            # zone transition voice
            if zone != self.last_zone and self.focus_mode:
                try:
                    from voice_output import speak_elevated
                    if zone == "ELEVATED":
                        speak_elevated()
                except Exception:
                    pass

            self.last_zone = zone

            # ── Hand on face/head — READ FROM vision_state not signals ──
            hof = self.vision_state.get("hand_on_face", False)
            hoh = self.vision_state.get("hand_on_head", False)
            now = time.time()
            currently_detected = hof or hoh
            # fire on: NEW detection (was off, now on) OR every 20s while持续
            just_raised = currently_detected and not self._hand_was_detected
            cooldown_ok = (now - self._last_hand_voice) > 20
            if currently_detected and (just_raised or cooldown_ok):
                print(f"[AGENT] Hand gesture: face={hof} head={hoh} — SPEAKING NOW")
                try:
                    from voice_output import speak_hand_detected
                    speak_hand_detected()
                except Exception as e:
                    print(f"[AGENT] hand voice error: {e}")
                self._last_hand_voice = now
                if self.dashboard:
                    msg = "Hand on your head — you okay? Breathe 🌿" if hoh else "Hand on your face — take a breath 🌿"
                    self.dashboard.notify_stress(msg)
            self._hand_was_detected = currently_detected

            self.cooldown_secs = self.memory.get_adapted_cooldown()
            self.maybe_auto_focus(score, zone, signals)

            if not self.focus_mode:
                continue

            cooldown_ok = (now - self.last_intervention) > self.cooldown_secs
            if zone in ("OVERLOAD", "RAGE") and cooldown_ok:
                action = self._get_action(zone, signals, score)
                if action:
                    log = f"{time.strftime('%H:%M')} – {action} (score {score})"
                    if self.ui_callback:
                        self.ui_callback({"score": score, "zone": zone, "signals": signals, "log": log})
                    idx = self.memory.record_intervention(action, score, zone)
                    self._execute(action)
                    self.last_intervention = now
                    self._observe_outcome(idx, score)

    def start(self):
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()
        print("[AGENT] CLR Agent started.")