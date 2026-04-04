# vision_pipeline.py — fixed for close-camera setup
import threading, time, cv2

MEDIAPIPE_OK = False
try:
    import mediapipe as mp
    try:
        _ = mp.solutions.face_mesh
        _ = mp.solutions.hands
        MEDIAPIPE_OK = True
    except AttributeError:
        pass
except ImportError:
    pass

class VisionPipeline:
    LEFT_EYE  = [33, 160, 158, 133, 153, 144]
    RIGHT_EYE = [362, 385, 387, 263, 373, 380]

    def __init__(self):
        self.state = {
            "face_present": False, "eye_state": "unknown",
            "stressed_face": False, "mouth_open": False,
            "hand_on_face": False, "hand_on_head": False,
            "stress_gestures": 0,
        }
        self._hof_frames = 0
        self._hoh_frames = 0
        self._eye_frames = 0
        self._mouth_frames = 0
        self._init_detectors()
        self._cap = cv2.VideoCapture(0)
        threading.Thread(target=self._loop, daemon=True).start()

    def _init_detectors(self):
        global MEDIAPIPE_OK
        if not MEDIAPIPE_OK:
            self._face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            print("[VISION] haar fallback"); return
        try:
            import mediapipe as mp
            self._face_mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1, refine_landmarks=True,
                min_detection_confidence=0.4, min_tracking_confidence=0.4)
            self._hands = mp.solutions.hands.Hands(
                max_num_hands=2,
                min_detection_confidence=0.4, min_tracking_confidence=0.4)
            print("[VISION] mediapipe ready")
        except Exception as e:
            print(f"[VISION] init error: {e}")
            MEDIAPIPE_OK = False

    def _ear(self, lm, idx, w, h):
        pts = [(lm[i].x*w, lm[i].y*h) for i in idx]
        v = abs(pts[1][1]-pts[5][1]) + abs(pts[2][1]-pts[4][1])
        hz = abs(pts[0][0]-pts[3][0])
        return v / (2*hz) if hz > 0 else 0.3

    def _analyse(self, frame):
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        fr = self._face_mesh.process(rgb)
        hr = self._hands.process(rgb)
        rgb.flags.writeable = True

        face_present = False
        eye_state = "unknown"
        mouth_open = False
        found_hof = False
        found_hoh = False

        # face box defaults (centre of frame)
        fx_min, fx_max = 0.3, 0.7
        fy_min, fy_max = 0.2, 0.8

        if fr.multi_face_landmarks:
            face_present = True
            lm = fr.multi_face_landmarks[0].landmark

            # EAR
            ear = (self._ear(lm, self.LEFT_EYE, w, h) +
                   self._ear(lm, self.RIGHT_EYE, w, h)) / 2
            if ear < 0.18: self._eye_frames += 1
            else:          self._eye_frames = max(0, self._eye_frames - 1)
            eye_state = "closed" if ear < 0.14 else ("strained" if self._eye_frames >= 8 else "open")

            # mouth
            vert  = abs(lm[14].y - lm[13].y) * h
            horiz = abs(lm[308].x - lm[78].x) * w
            if horiz > 0 and vert/horiz > 0.35: self._mouth_frames += 1
            else: self._mouth_frames = max(0, self._mouth_frames - 1)
            mouth_open = self._mouth_frames >= 4

            xs = [l.x for l in lm]; ys = [l.y for l in lm]
            fx_min = min(xs) - 0.05
            fx_max = max(xs) + 0.05
            fy_min = min(ys) - 0.05
            fy_max = max(ys) + 0.05

        if hr.multi_hand_landmarks:
            for hlm in hr.multi_hand_landmarks:
                lms = hlm.landmark
                # FINGERTIPS: 4=thumb, 8=index, 12=middle, 16=ring, 20=pinky
                # MCP knuckles: 5, 9, 13, 17
                fingertips = [lms[i] for i in [4, 8, 12, 16, 20]]
                knuckles   = [lms[i] for i in [5, 9, 13, 17]]
                all_pts    = fingertips + knuckles + [lms[0]]  # +wrist

                for pt in all_pts:
                    px, py = pt.x, pt.y

                    # hand ON face: any point inside face bounding box
                    if fx_min < px < fx_max and fy_min < py < fy_max:
                        found_hof = True
                        break

                # hand ON HEAD: fingertips in upper portion of frame
                # Your face y starts ~0.32, so fingertips above 0.40 = on head
                for tip in fingertips:
                    if tip.y < 0.45:   # upper 45% of frame = on/above head
                        found_hoh = True
                        break

                # Also: if multiple fingertips are ABOVE the face top
                tips_above_face = sum(1 for t in fingertips if t.y < fy_min + 0.05)
                if tips_above_face >= 2:
                    found_hoh = True

                if found_hof or found_hoh:
                    print(f"[VISION] GESTURE: hof={found_hof} hoh={found_hoh} "
                          f"tips_y={[round(t.y,2) for t in fingertips]}")

        # frame counters
        if found_hof: self._hof_frames += 1
        else:         self._hof_frames = max(0, self._hof_frames - 1)
        if found_hoh: self._hoh_frames += 1
        else:         self._hoh_frames = max(0, self._hoh_frames - 1)

        return face_present, eye_state, mouth_open, self._hof_frames >= 3, self._hoh_frames >= 3

    def _loop(self):
        while True:
            ok, frame = self._cap.read()
            if not ok:
                time.sleep(0.5); continue
            try:
                if MEDIAPIPE_OK:
                    fp, eye, mouth, hof, hoh = self._analyse(frame)
                else:
                    gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = self._face_cascade.detectMultiScale(gray, 1.3, 5)
                    fp, eye, mouth, hof, hoh = len(faces) > 0, "open", False, False, False
            except Exception as e:
                print(f"[VISION] error: {e}"); time.sleep(0.5); continue

            stressed  = (eye == "strained") or hof or hoh
            gestures  = self.state.get("stress_gestures", 0) + (1 if (hof or hoh) else 0)
            self.state = {
                "face_present": fp, "eye_state": eye,
                "stressed_face": stressed, "mouth_open": mouth,
                "hand_on_face": hof, "hand_on_head": hoh,
                "stress_gestures": gestures,
            }
            time.sleep(0.15)

    def get_state(self):
        return dict(self.state)