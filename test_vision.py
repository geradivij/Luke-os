# test_vision.py — run this standalone to check camera + mediapipe
import cv2
import sys

print("Testing camera...")
cap = cv2.VideoCapture(0)
ok, frame = cap.read()
if not ok:
    print("❌ Camera FAILED — cannot read frame. Check if another app is using it.")
    sys.exit(1)
else:
    print(f"✅ Camera OK — frame shape: {frame.shape}")

print("\nTesting mediapipe...")
try:
    import mediapipe as mp
    print(f"✅ mediapipe imported, version: {mp.__version__}")

    face_mesh = mp.solutions.face_mesh.FaceMesh(
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.3,
        min_tracking_confidence=0.3,
    )
    hands = mp.solutions.hands.Hands(
        max_num_hands=2,
        min_detection_confidence=0.3,
        min_tracking_confidence=0.3,
    )
    print("✅ Face mesh + hands models loaded")

    print("\nReading 30 frames — sit in front of camera and put hand up...")
    for i in range(30):
        ok, frame = cap.read()
        if not ok:
            continue
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_result  = face_mesh.process(rgb)
        hands_result = hands.process(rgb)

        face_found = face_result.multi_face_landmarks is not None
        hand_found = hands_result.multi_hand_landmarks is not None

        if face_found or hand_found:
            hand_pos = ""
            if hand_found:
                w = hands_result.multi_hand_landmarks[0].landmark[0]
                hand_pos = f" | hand wrist=({w.x:.2f},{w.y:.2f})"
            print(f"  Frame {i+1:02d}: face={face_found} hand={hand_found}{hand_pos}")
        else:
            print(f"  Frame {i+1:02d}: nothing detected")

        import time; time.sleep(0.1)

    face_mesh.close()
    hands.close()

except Exception as e:
    print(f"❌ mediapipe error: {e}")

cap.release()
print("\nDone.")