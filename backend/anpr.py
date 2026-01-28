import cv2
import time
import csv
import os
import re
from datetime import datetime
from ultralytics import YOLO
import easyocr
from vehicle_db import VEHICLE_DB
from gate_controller import gate_manager

# ================= CONFIG =================
CAMERA_INDEX = 0
CONF_THRESHOLD = 0.4
LOG_FILE = "logs.csv"
SNAP_DIR = "snapshots"
STUDENT_START = 6
STUDENT_END = 22

# ================= GLOBAL STATE =================
latest_frame = None
latest_detection = {}
gate_state = {"status": "WAITING", "reason": "", "updated": ""}
alerts = []
plate_votes = {} # Buffer to prevent flickering

# ================= COLORS =================
GREEN, RED, YELLOW = (0, 255, 0), (0, 0, 255), (0, 255, 255)

# ================= MODELS =================
model = YOLO("license_plate_detector.pt")
reader = easyocr.Reader(["en"], gpu=False)

# ================= HELPERS =================
def clean_plate(text):
    text = re.sub(r"[^A-Z0-9]", "", text.upper().strip())
    if len(text) < 7: return ""
    char_map = {'4': 'H', '0': 'O', '1': 'I', '5': 'S', '8': 'B', '2': 'Z'}
    num_map = {'H': '4', 'I': '1', 'O': '0', 'S': '5', 'B': '8', 'Z': '2'}
    chars = list(text)
    for i in range(min(2, len(chars))):
        if chars[i] in char_map: chars[i] = char_map[chars[i]]
    for i in range(2, min(4, len(chars))):
        if i < len(chars) and chars[i] in num_map: chars[i] = num_map[chars[i]]
    fixed = "".join(chars)
    return fixed if 7 <= len(fixed) <= 11 else ""

def get_vehicle_type(plate):
    return VEHICLE_DB.get(plate, {"type": "Visitor"})["type"]

def student_time_allowed():
    return STUDENT_START <= datetime.now().hour < STUDENT_END

def ensure_files():
    os.makedirs(SNAP_DIR, exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            csv.writer(f).writerow(["timestamp", "plate", "type", "confidence", "snapshot"])

# ================= MAIN LOOP =================
def main():
    global latest_frame, latest_detection, gate_state, alerts
    ensure_files()
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    print("✅ ANPR SYSTEM ACTIVE")

    while True:
        ret, frame = cap.read()
        if not ret: continue
        display_frame = frame.copy()
        results = model(frame, conf=CONF_THRESHOLD, verbose=False)

        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                plate_crop = frame[y1:y2, x1:x2]
                if plate_crop.size == 0: continue

                ocr = reader.readtext(plate_crop)
                if not ocr: continue

                plate = clean_plate(ocr[0][1])
                if not plate: continue

                # Voting Logic: Only act if plate seen 3 times
                plate_votes[plate] = plate_votes.get(plate, 0) + 1
                if plate_votes[plate] >= 3:
                    confidence = int(box.conf[0] * 100)
                    vehicle_type = get_vehicle_type(plate)
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    # Decision Logic via Gate Manager
                    status, reason = gate_manager.evaluate_access(plate, vehicle_type)
                    
                    # Handle Student specific time rule
                    if vehicle_type == "Student" and not student_time_allowed():
                        status, reason = "BLOCK", "Student Outside Hours"

                    # Set Display Colors
                    color = RED if status == "BLOCK" else GREEN if status == "OPEN" else YELLOW
                    
                    # Log and Save Snapshot
                    snap_name = f"{plate}_{int(time.time())}.jpg"
                    cv2.imwrite(os.path.join(SNAP_DIR, snap_name), frame)

                    # Update Global States
                    latest_detection = {
                        "timestamp": ts, "plate": plate, "type": vehicle_type,
                        "confidence": confidence, "snapshot": snap_name, "status": status
                    }
                    gate_state.update({"status": status, "reason": reason, "updated": ts})

                    # Draw Bounding Box
                    cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 3)
                    cv2.rectangle(display_frame, (x1, y1 - 35), (x2, y1), color, -1)
                    cv2.putText(display_frame, f"{plate} | {status}", (x1 + 5, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                    with open(LOG_FILE, "a", newline="") as f:
                        csv.writer(f).writerow([ts, plate, vehicle_type, confidence, snap_name])

                    plate_votes[plate] = 0 # Reset votes for this plate
                    time.sleep(0.5)

        latest_frame = display_frame
        if cv2.waitKey(1) & 0xFF == ord('q'): break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()