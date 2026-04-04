# test_vision2.py — shows face box coords so we can calibrate
import cv2, time, mediapipe as mp

cap = cv2.VideoCapture(0)
face_mesh = mp.solutions.face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=True,
    min_detection_confidence=0.3, min_tracking_confidence=0.3)
hands = mp.solutions.hands.Hands(max_num_hands=2,
    min_detection_confidence=0.3, min_tracking_confidence=0.3)

print("Put your hand on your HEAD and hold it for 5 seconds...")
for i in range(50):
    ok, frame = cap.read()
    if not ok: continue
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    fr = face_mesh.process(rgb)
    hr = hands.process(rgb)

    if fr.multi_face_landmarks:
        lm = fr.multi_face_landmarks[0].landmark
        xs = [l.x for l in lm]; ys = [l.y for l in lm]
        fx_min, fx_max = min(xs)-0.08, max(xs)+0.08
        fy_min, fy_max = min(ys)-0.08, max(ys)+0.12
        print(f"  Face box: x={fx_min:.2f}-{fx_max:.2f}  y={fy_min:.2f}-{fy_max:.2f}")

        if hr.multi_hand_landmarks:
            for hlm in hr.multi_hand_landmarks:
                wx = hlm.landmark[0].x; wy = hlm.landmark[0].y
                in_face = fx_min < wx < fx_max and fy_min < wy < fy_max
                above   = fx_min-0.2 < wx < fx_max+0.2 and wy < fy_min+0.08
                print(f"  Hand wrist: ({wx:.2f},{wy:.2f})  in_face={in_face}  above_face={above}  --> HOH would be: wy<{fy_min+0.08:.2f}")
    time.sleep(0.1)

cap.release()