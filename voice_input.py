# voice_input.py — uses sounddevice + numpy (no pyaudio needed)

import threading
import numpy as np
import queue

try:
    import sounddevice as sd
    SOUNDDEVICE_OK = True
except ImportError:
    SOUNDDEVICE_OK = False

try:
    import speech_recognition as sr
    SR_OK = True
except ImportError:
    SR_OK = False

STRESS_PHRASES = [
    "i am so stressed", "i'm so stressed", "so stressed",
    "i am stressed", "i'm stressed", "stressed out",
    "i can't do this", "i cant do this",
    "this is too much", "overwhelmed",
    "i give up", "i need a break",
    "i hate this", "so frustrating", "frustrated",
    "ugh", "argh",
]


class VoiceListener:
    def __init__(self, on_stress_detected=None):
        self.on_stress_detected = on_stress_detected
        self.running = False

    def _matches_stress(self, text: str) -> bool:
        t = text.lower().strip()
        return any(phrase in t for phrase in STRESS_PHRASES)

    def _listen_loop_sr(self):
        """Primary: use SpeechRecognition with default mic."""
        import speech_recognition as sr
        r = sr.Recognizer()
        r.energy_threshold = 300
        r.dynamic_energy_threshold = True
        print("[VOICE_IN] Listening with SpeechRecognition...")
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=1)
            while self.running:
                try:
                    audio = r.listen(source, timeout=4, phrase_time_limit=6)
                    text = r.recognize_google(audio)
                    print(f"[VOICE_IN] Heard: '{text}'")
                    if self._matches_stress(text):
                        print("[VOICE_IN] Stress detected!")
                        if self.on_stress_detected:
                            self.on_stress_detected(text)
                except sr.WaitTimeoutError:
                    pass
                except sr.UnknownValueError:
                    pass
                except sr.RequestError as e:
                    print(f"[VOICE_IN] SR error: {e}")
                except Exception as e:
                    print(f"[VOICE_IN] error: {e}")

    def _listen_loop_sounddevice(self):
        """
        Fallback: use sounddevice to record chunks, then feed to
        SpeechRecognition via AudioData.
        """
        import speech_recognition as sr
        r = sr.Recognizer()
        RATE = 16000
        CHUNK_SECS = 4
        print("[VOICE_IN] Listening with sounddevice fallback...")

        while self.running:
            try:
                recording = sd.rec(
                    int(CHUNK_SECS * RATE),
                    samplerate=RATE,
                    channels=1,
                    dtype="int16",
                    blocking=True,
                )
                audio_bytes = recording.tobytes()
                audio_data = sr.AudioData(audio_bytes, RATE, 2)
                text = r.recognize_google(audio_data)
                print(f"[VOICE_IN] Heard: '{text}'")
                if self._matches_stress(text):
                    print("[VOICE_IN] Stress detected!")
                    if self.on_stress_detected:
                        self.on_stress_detected(text)
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"[VOICE_IN] SR error: {e}")
            except Exception as e:
                print(f"[VOICE_IN] error: {e}")

    def start(self):
        if not SR_OK:
            print("[VOICE_IN] SpeechRecognition not installed — voice input disabled.")
            print("[VOICE_IN] Run: pip install SpeechRecognition")
            return

        self.running = True

        # Try SpeechRecognition with built-in mic first, fall back to sounddevice
        try:
            import speech_recognition as sr
            sr.Microphone()  # test if pyaudio mic works
            t = threading.Thread(target=self._listen_loop_sr, daemon=True)
        except Exception:
            if SOUNDDEVICE_OK:
                print("[VOICE_IN] pyaudio mic unavailable, using sounddevice fallback")
                t = threading.Thread(target=self._listen_loop_sounddevice, daemon=True)
            else:
                print("[VOICE_IN] No audio backend available — voice input disabled.")
                return

        t.start()

    def stop(self):
        self.running = False