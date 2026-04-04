"""
productivity.py
===============
Extracted from Productivity Illusion Breaker notebook.
Runs as a background thread alongside supermemory agents.

Provides:
  - DeviceTracker     → continuous keyboard/mouse/app sampling
  - build_features()  → derives behavioral features from samples
  - score_features()  → productivity_score, retention_score (0-100)
  - detect_fake_productivity() → risk level + pattern messages
  - get_current_snapshot()    → called per screenshot to attach scores

No DB. No notebook boilerplate. Thread-safe via a single lock.
"""

import math
import time
import platform
import subprocess
import threading
from datetime import datetime

# ── Config (mirrors notebook) ─────────────────────────────────────────────────

SAMPLE_INTERVAL       = 1.0
IDLE_THRESHOLD_SECONDS = 60

DISTRACTING_KEYWORDS = [
    "youtube", "facebook", "instagram", "tiktok", "twitter", "x.com",
    "reddit", "netflix", "steam", "discord", "twitch", "spotify",
]

WEIGHTS = {
    "focus":      0.35,
    "depth":      0.20,
    "engagement": 0.15,
    "switching":  0.15,
    "idle":       0.15,
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def clamp(value, low=0, high=100):
    return max(low, min(high, value))


def get_foreground_window_title() -> str:
    try:
        if platform.system() == "Darwin":
            cmd = [
                "osascript", "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            title = (result.stdout or "").strip()
            return title if title else "Unknown"
        if platform.system() == "Windows":
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value or "Unknown"
        return "Unknown"
    except Exception:
        return "Unknown"


# ── Feature building (unchanged from notebook) ────────────────────────────────

def build_features(samples: list, switch_count: int) -> dict:
    if not samples:
        return {}

    duration_seconds = max(1, len(samples))
    first = samples[0]
    last  = samples[-1]

    key_delta    = last["key_total"]    - first["key_total"]
    click_delta  = last["click_total"]  - first["click_total"]
    scroll_delta = last["scroll_total"] - first["scroll_total"]
    total_inputs = max(0, key_delta + click_delta + scroll_delta)

    idle_seconds = sum(1 for s in samples if s["idle_seconds"] >= IDLE_THRESHOLD_SECONDS)
    active_seconds = duration_seconds - idle_seconds

    distracting_seconds = sum(
        1 for s in samples
        if any(
            word in (s["app_title"] or "").lower()
            for word in DISTRACTING_KEYWORDS
        )
    )

    longest_streak = current_streak = 1
    for i in range(1, len(samples)):
        prev = samples[i - 1]
        cur  = samples[i]
        if (cur["app_title"] == prev["app_title"]
                and cur["idle_seconds"]  < IDLE_THRESHOLD_SECONDS
                and prev["idle_seconds"] < IDLE_THRESHOLD_SECONDS):
            current_streak += 1
        else:
            longest_streak = max(longest_streak, current_streak)
            current_streak = 1
    longest_streak = max(longest_streak, current_streak)

    unique_apps          = len(set(s["app_title"] for s in samples))
    input_rate_per_min   = (total_inputs / duration_seconds) * 60.0
    focus_ratio          = active_seconds / duration_seconds
    idle_ratio           = idle_seconds   / duration_seconds
    distraction_ratio    = distracting_seconds / duration_seconds
    switch_rate_per_min  = (switch_count / duration_seconds) * 60.0

    return {
        "duration_seconds":      duration_seconds,
        "active_seconds":        active_seconds,
        "idle_seconds":          idle_seconds,
        "switch_count":          switch_count,
        "unique_apps":           unique_apps,
        "total_inputs":          total_inputs,
        "input_rate_per_min":    input_rate_per_min,
        "longest_streak_seconds": longest_streak,
        "focus_ratio":           focus_ratio,
        "idle_ratio":            idle_ratio,
        "distraction_ratio":     distraction_ratio,
        "switch_rate_per_min":   switch_rate_per_min,
    }


def score_features(features: dict) -> dict:
    if not features:
        return {}

    focus_score      = clamp(features["focus_ratio"] * 100)
    depth_score      = clamp((features["longest_streak_seconds"] / 25.0) * 100)
    engagement_score = clamp(math.log1p(features["input_rate_per_min"]) * 30)
    switching_score  = clamp(100 - (features["switch_rate_per_min"] * 4.5))
    idle_score       = clamp(100 - (features["idle_ratio"] * 120))

    base = (
        WEIGHTS["focus"]      * focus_score
        + WEIGHTS["depth"]      * depth_score
        + WEIGHTS["engagement"] * engagement_score
        + WEIGHTS["switching"]  * switching_score
        + WEIGHTS["idle"]       * idle_score
    )

    distraction_penalty  = features["distraction_ratio"] * 30
    productivity_score   = clamp(base - distraction_penalty)

    if features["duration_seconds"] < 60:
        productivity_score *= max(0.5, features["duration_seconds"] / 60)

    retention_score = clamp(
        0.40 * depth_score
        + 0.25 * focus_score
        + 0.15 * engagement_score
        + 0.20 * switching_score
        - (features["distraction_ratio"] * 25)
    )

    return {
        "focus_score":        round(focus_score, 2),
        "depth_score":        round(depth_score, 2),
        "engagement_score":   round(engagement_score, 2),
        "switching_score":    round(switching_score, 2),
        "idle_score":         round(idle_score, 2),
        "productivity_score": round(productivity_score, 2),
        "retention_score":    round(retention_score, 2),
    }


def detect_fake_productivity(features: dict, scores: dict) -> tuple[str, list[str]]:
    messages = []
    duration_min = features["duration_seconds"] / 60.0

    if duration_min >= 20 and features["switch_rate_per_min"] >= 6:
        messages.append("Frequent switching detected — likely shallow work.")
    if duration_min >= 20 and features["focus_ratio"] < 0.55:
        messages.append("Low sustained focus — time spent may not translate into results.")
    if features["idle_ratio"] >= 0.25:
        messages.append("High idle time — session contains long inactive gaps.")
    if features["longest_streak_seconds"] < 25 and duration_min >= 20:
        messages.append("Short interrupted sessions — deep work is not happening.")
    if features["distraction_ratio"] >= 0.30:
        messages.append("Large portion of session in distracting apps.")
    if scores.get("productivity_score", 0) >= 75 and scores.get("retention_score", 0) < 50:
        messages.append("Productivity looks high but retention appears weak.")
    if features["switch_count"] >= 3 and features["duration_seconds"] < 60:
        messages.append("High switching in short session — lack of focus.")

    if not messages:
        messages.append("No major fake-productivity pattern detected.")

    score = scores.get("productivity_score", 0)
    risk  = "Low" if score >= 80 else "Medium" if score >= 60 else "High"
    return risk, messages


# ── DeviceTracker — runs as daemon thread ─────────────────────────────────────

class DeviceTracker:
    """
    Continuously samples keyboard, mouse, and foreground app.
    Exposes get_snapshot() for supermemory to call per screenshot.
    No blocking run() — starts immediately in background.
    """

    def __init__(self):
        self.lock           = threading.Lock()
        self.samples: list  = []
        self.key_total      = 0
        self.click_total    = 0
        self.scroll_total   = 0
        self.last_input_ts  = time.time()
        self.prev_app       = None
        self.switch_count   = 0
        self._stop          = threading.Event()
        self._kb_listener   = None
        self._ms_listener   = None

    # ── Input listeners ───────────────────────────────────────────────────────

    def _on_key(self, key):
        with self.lock:
            self.key_total    += 1
            self.last_input_ts = time.time()

    def _on_click(self, x, y, button, pressed):
        if pressed:
            with self.lock:
                self.click_total  += 1
                self.last_input_ts = time.time()

    def _on_scroll(self, x, y, dx, dy):
        with self.lock:
            self.scroll_total += 1
            self.last_input_ts = time.time()

    # ── Sampling loop ─────────────────────────────────────────────────────────

    def _sample_loop(self):
        while not self._stop.is_set():
            app = get_foreground_window_title()
            with self.lock:
                idle = time.time() - self.last_input_ts
                self.samples.append({
                    "ts":           datetime.now().isoformat(timespec="seconds"),
                    "app_title":    app,
                    "idle_seconds": idle,
                    "key_total":    self.key_total,
                    "click_total":  self.click_total,
                    "scroll_total": self.scroll_total,
                })
                # track app switches
                if self.prev_app is not None and app != self.prev_app:
                    self.switch_count += 1
                self.prev_app = app

                # keep rolling window — last 600 samples (10 min at 1s)
                if len(self.samples) > 600:
                    self.samples = self.samples[-600:]

            self._stop.wait(SAMPLE_INTERVAL)

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Start sampling + listeners in background. Call once."""
        try:
            from pynput import keyboard as kb, mouse as ms
            self._kb_listener = kb.Listener(on_press=self._on_key)
            self._ms_listener = ms.Listener(on_click=self._on_click, on_scroll=self._on_scroll)
            self._kb_listener.start()
            self._ms_listener.start()
        except Exception:
            pass  # pynput not available — still track apps + idle

        t = threading.Thread(target=self._sample_loop, daemon=True, name="productivity-sampler")
        t.start()

    def stop(self):
        self._stop.set()
        try:
            if self._kb_listener: self._kb_listener.stop()
            if self._ms_listener: self._ms_listener.stop()
        except Exception:
            pass

    def get_snapshot(self) -> dict:
        """
        Returns current productivity scores computed from all samples so far.
        Safe to call from any thread. Returns empty dict if < 5 samples.
        """
        with self.lock:
            samples_copy  = list(self.samples)
            switch_count  = self.switch_count

        if len(samples_copy) < 5:
            return {"productivity_score": None, "risk_level": None, "note": "warming up"}

        features = build_features(samples_copy, switch_count)
        scores   = score_features(features)
        risk, patterns = detect_fake_productivity(features, scores)

        return {
            "productivity_score": scores.get("productivity_score"),
            "retention_score":    scores.get("retention_score"),
            "focus_score":        scores.get("focus_score"),
            "risk_level":         risk,
            "is_distracted":      features.get("distraction_ratio", 0) >= 0.3,
            "switch_count":       switch_count,
            "idle_ratio":         round(features.get("idle_ratio", 0), 2),
            "patterns":           patterns,
            "samples_collected":  len(samples_copy),
        }