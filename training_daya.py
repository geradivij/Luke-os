# training_data.py

TRAINING_EXAMPLES = [
    # 1) Overthinking in Slack/Discord – high load, many backspaces
    ({"app_switches_30s": 3, "backspace_bursts": 4, "idle_secs": 3,
      "face_present": True, "eye_state": "open", "load_score": 82,
      "active_app": "slack"},
     "hide_chat_and_focus_work"),

    ({"app_switches_30s": 2, "backspace_bursts": 5, "idle_secs": 2,
      "face_present": True, "eye_state": "strained", "load_score": 88,
      "active_app": "discord"},
     "hide_chat_and_focus_work"),

    ({"app_switches_30s": 4, "backspace_bursts": 6, "idle_secs": 4,
      "face_present": True, "eye_state": "strained", "load_score": 91,
      "active_app": "slack"},
     "rage_break"),

    # 2) Staring at chat – idle but face present
    ({"app_switches_30s": 1, "backspace_bursts": 0, "idle_secs": 50,
      "face_present": True, "eye_state": "open", "load_score": 68,
      "active_app": "slack"},
     "soft_nudge"),

    ({"app_switches_30s": 0, "backspace_bursts": 0, "idle_secs": 70,
      "face_present": True, "eye_state": "open", "load_score": 72,
      "active_app": "discord"},
     "soft_nudge"),

    # 3) Tired eyes – need a walk
    ({"app_switches_30s": 1, "backspace_bursts": 1, "idle_secs": 80,
      "face_present": True, "eye_state": "closed", "load_score": 78,
      "active_app": "chrome"},
     "enforce_break"),

    ({"app_switches_30s": 0, "backspace_bursts": 0, "idle_secs": 90,
      "face_present": True, "eye_state": "closed", "load_score": 85,
      "active_app": "slack"},
     "enforce_break"),

    # 4) Rage – everything spiking
    ({"app_switches_30s": 8, "backspace_bursts": 7, "idle_secs": 0,
      "face_present": True, "eye_state": "strained", "load_score": 95,
      "active_app": "slack"},
     "rage_break"),

    ({"app_switches_30s": 7, "backspace_bursts": 5, "idle_secs": 0,
      "face_present": True, "eye_state": "strained", "load_score": 93,
      "active_app": "discord"},
     "rage_break"),

    # 5) Deep work in VSCode – don’t touch
    ({"app_switches_30s": 1, "backspace_bursts": 1, "idle_secs": 5,
      "face_present": True, "eye_state": "open", "load_score": 40,
      "active_app": "vscode"},
     "no_action"),

    ({"app_switches_30s": 0, "backspace_bursts": 0, "idle_secs": 10,
      "face_present": False, "eye_state": "unknown", "load_score": 20,
      "active_app": "vscode"},
     "no_action"),

    # 6) Light chat usage – no need to intervene
    ({"app_switches_30s": 1, "backspace_bursts": 0, "idle_secs": 8,
      "face_present": True, "eye_state": "open", "load_score": 35,
      "active_app": "slack"},
     "no_action"),

    ({"app_switches_30s": 2, "backspace_bursts": 1, "idle_secs": 5,
      "face_present": True, "eye_state": "open", "load_score": 45,
      "active_app": "discord"},
     "no_action"),

    # 7) Browsing / research – maybe soft nudge at high load
    ({"app_switches_30s": 5, "backspace_bursts": 2, "idle_secs": 10,
      "face_present": True, "eye_state": "open", "load_score": 70,
      "active_app": "chrome"},
     "soft_nudge"),

    ({"app_switches_30s": 6, "backspace_bursts": 3, "idle_secs": 5,
      "face_present": True, "eye_state": "strained", "load_score": 80,
      "active_app": "chrome"},
     "enforce_break"),

    # 8) Confused but not overloaded – gentle nudge
    ({"app_switches_30s": 2, "backspace_bursts": 0, "idle_secs": 60,
      "face_present": True, "eye_state": "open", "load_score": 55,
      "active_app": "vscode"},
     "soft_nudge"),

    # Duplicate patterns with slight noise to reach ~60 examples
]

# Create more noisy variations programmatically
def format_examples():
    formatted = []
    base = TRAINING_EXAMPLES.copy()

    # Simple augmentation: vary load_score and counts a bit
    for state, action in base:
        formatted.append({"prompt": state, "action": action})

        s2 = state.copy()
        s2["load_score"] = max(0, min(100, state["load_score"] + 5))
        formatted.append({"prompt": s2, "action": action})

        s3 = state.copy()
        s3["app_switches_30s"] = max(0, state["app_switches_30s"] - 1)
        formatted.append({"prompt": s3, "action": action})

    return formatted
