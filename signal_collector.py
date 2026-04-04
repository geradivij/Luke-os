# signal_collector.py
import time, threading, collections
from pynput import keyboard, mouse

try:
    import pygetwindow as gw
    def GET_WINDOW():
        w = gw.getActiveWindow()
        return w.title if w else ''
except Exception:
    GET_WINDOW = lambda: ''


class SignalCollector:
    def __init__(self, window_secs=30):
        self.window_secs = window_secs
        self.backspace_times = collections.deque()
        self.window_switches = collections.deque()
        self.last_activity = time.time()
        self.last_window = ''
        self.backspace_burst_count = 0

        # new fields for calls
        self.active_app = ''
        self.app_enter_time = time.time()

        self._start_listeners()

    def _start_listeners(self):
        # Keyboard
        def on_key(key):
            self.last_activity = time.time()
            if key == keyboard.Key.backspace:
                self.backspace_times.append(time.time())
        keyboard.Listener(on_press=on_key).start()

        # Mouse
        def on_move(x, y):
            self.last_activity = time.time()
        mouse.Listener(on_move=on_move).start()

        # App switch + call tracker
        def poll_window():
            while True:
                try:
                    w = GET_WINDOW()
                    if w and w != self.last_window:
                        self.window_switches.append(time.time())
                        self.last_window = w
                        self.active_app = w
                        self.app_enter_time = time.time()
                except Exception:
                    pass
                time.sleep(1)

        threading.Thread(target=poll_window, daemon=True).start()

    def _prune(self, dq, cutoff):
        while dq and dq[0] < cutoff:
            dq.popleft()

    def get_state(self, vision_state=None):
        now = time.time()
        cutoff = now - self.window_secs

        self._prune(self.window_switches, cutoff)
        self._prune(self.backspace_times, cutoff)

        switches = len(self.window_switches)

        # backspace bursts: 5+ in 3s
        bs = list(self.backspace_times)
        bursts = 0
        j = 0
        for i in range(len(bs)):
            while j < len(bs) and bs[j] - bs[i] <= 3:
                j += 1
            if (j - i) >= 5:
                bursts += 1

        idle_secs = int(now - self.last_activity)

        eye_state = vision_state.get('eye_state', 'unknown') if vision_state else 'unknown'
        face_present = vision_state.get('face_present', True) if vision_state else True
        stressed_face = vision_state.get('stressed_face', False) if vision_state else False

        # call tracking
        in_app_secs = now - self.app_enter_time
        app_lower = self.active_app.lower() if self.active_app else ""
        on_call = any(x in app_lower for x in ["zoom", "meet", "teams", "webex", "huddle", "call", "phone"])
        call_minutes = int(in_app_secs / 60) if on_call else 0

        return {
            'app_switches_30s': switches,
            'backspace_bursts': bursts,
            'idle_secs': idle_secs,
            'face_present': face_present,
            'eye_state': eye_state,
            'stressed_face': stressed_face,
            'active_app': self.active_app,
            'on_call': on_call,
            'call_minutes': call_minutes,
        }


if __name__ == '__main__':
    sc = SignalCollector()
    print('Collecting signals... (switch apps, move mouse, spam backspace)')
    for _ in range(12):
        time.sleep(5)
        print(sc.get_state())
