# voice_output.py — each call creates fresh engine, no "run loop" error
import random
import threading

def speak_text(text: str):
    def _speak():
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 150)
            engine.setProperty("volume", 0.95)
            voices = engine.getProperty("voices")
            for v in voices:
                if any(x in v.name.lower() for x in ["zira", "hazel", "female"]):
                    engine.setProperty("voice", v.id)
                    break
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception as ex:
            print(f"[VOICE] error: {ex}")
    threading.Thread(target=_speak, daemon=True).start()

RAGE_LINES = [
    "Okay, things got spicy. Closing the noise. Five minutes, just breathe.",
    "You're in the red. Distractions are gone. Step away for a bit.",
    "Way too much going on. Shutting it all down. You've earned a break.",
]
OVERLOAD_LINES = [
    "Getting loaded up. Muting the noise so you can find your flow.",
    "Too many apps. Closing the chaos. You've got this.",
    "High load. Let me clear the clutter.",
]
ELEVATED_LINES = [
    "Things are heating up. I'm keeping an eye on you.",
    "Load is rising. Take a breath.",
]
ENFORCE_BREAK_LINES = [
    "Eyes look tired. Step away for three minutes.",
    "Three minute break. Look at something far away.",
]
NUDGE_LINES = [
    "That call's been running long. Your project is waiting.",
    "Long call. Deep work is calling when you're done.",
]
STRESS_COMFORT_LINES = [
    "Hey, I hear you. Take a breath. I'm right here.",
    "It's okay to feel overwhelmed. Let's slow down together.",
    "Don't give up yet. One thing at a time.",
]
HAND_LINES = [
    "Hey — hand on your head. You okay? Take a breath.",
    "I see that. Looks like you might be stressed. No rush.",
    "Hand on your face — take a second. You've got this.",
]
BREATHING_STILL_TENSE = [
    "Still a little tense. No pressure. Keep breathing.",
    "Take your time. I'm right here.",
]
BREATHING_RELAXED = [
    "That's it. You're looking more relaxed.",
    "Good. Take as long as you need.",
]
FOCUS_ON_LINES = [
    "Focus mode on. I'll protect your attention.",
    "Let's get in the zone. I'm watching your back.",
]
FOCUS_OFF_LINES = [
    "Focus mode off. Good session.",
    "Session ended. Nice work.",
]

def speak_rage():                  speak_text(random.choice(RAGE_LINES))
def speak_overload():              speak_text(random.choice(OVERLOAD_LINES))
def speak_elevated():              speak_text(random.choice(ELEVATED_LINES))
def speak_enforce_break():         speak_text(random.choice(ENFORCE_BREAK_LINES))
def speak_nudge():                 speak_text(random.choice(NUDGE_LINES))
def speak_stress_comfort():        speak_text(random.choice(STRESS_COMFORT_LINES))
def speak_hand_detected():         speak_text(random.choice(HAND_LINES))
def speak_breathing_still_tense(): speak_text(random.choice(BREATHING_STILL_TENSE))
def speak_breathing_relaxed():     speak_text(random.choice(BREATHING_RELAXED))
def speak_focus_on():              speak_text(random.choice(FOCUS_ON_LINES))
def speak_focus_off():             speak_text(random.choice(FOCUS_OFF_LINES))