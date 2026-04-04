# load_score.py — raised thresholds for demo
import time

class LoadScoreEngine:
    WEIGHTS = {
        'app_switches_30s': 8,
        'backspace_bursts':  6,
        'idle_with_face':    5,
        'eye_strained':      6,
        'stressed_face':     6,
        'hand_on_face':     12,  # raised — strong signal
        'hand_on_head':     10,  # raised — strong signal
    }

    ELEVATED_THRESHOLD = 25
    OVERLOAD_THRESHOLD = 50   # raised from 40
    RAGE_THRESHOLD     = 70   # raised from 60

    def __init__(self):
        self.history = []

    def compute(self, s: dict):
        score = 0
        score += min(s.get('app_switches_30s', 0), 8) * self.WEIGHTS['app_switches_30s']
        score += min(s.get('backspace_bursts',  0), 6) * self.WEIGHTS['backspace_bursts']
        if s.get('face_present', True) and s.get('idle_secs', 0) > 20:
            score += min(s['idle_secs'] // 10, 6) * self.WEIGHTS['idle_with_face']
        if s.get('eye_state') == 'strained':
            score += self.WEIGHTS['eye_strained']
        if s.get('stressed_face'):
            score += self.WEIGHTS['stressed_face']
        if s.get('hand_on_face'):
            score += self.WEIGHTS['hand_on_face']
        if s.get('hand_on_head'):
            score += self.WEIGHTS['hand_on_head']

        score = min(int(score), 100)
        self.history.append((time.time(), score))
        zone = (
            'RAGE'     if score >= self.RAGE_THRESHOLD     else
            'OVERLOAD' if score >= self.OVERLOAD_THRESHOLD else
            'ELEVATED' if score >= self.ELEVATED_THRESHOLD else
            'NORMAL'
        )
        return {'score': score, 'zone': zone}