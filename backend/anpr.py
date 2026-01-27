import cv2
import time
import csv
import os
import re
from datetime import datetime

from ultralytics import YOLO
import easyocr
from vehicle_db import VEHICLE_DB

# ================= CONFIG =================
CAMERA_INDEX = 0
CONF_THRESHOLD = 0.4
LOG_FILE = "logs.csv"
SNAP_DIR = "snapshots"

# Student allowed time (NIT Manipur rule)
STUDENT_START = 6   # 6 AM
STUDENT_END = 22    # 10 PM

# ================= GLOBAL STATE =================
latest_frame = None
latest_detection = {}
gate_state = {"status": "WAITING", "reason": "", "updated": ""}
alerts = []

# ================= COLORS =================
GREEN = (0, 255, 0)
RED = (0, 0, 255)
YELLOW = (0, 255, 255)

# ================= MODELS =================
print("🚀 Loading YOLOv8 plate detector...")
model = YOLO("license_plate_detector.pt")

print("🚀 Loading EasyOCR...")
reader = easyocr.Reader(["en"], gpu=False)

# ================= HELPERS =================
def clean_plate(text):
    text = re.sub(r"[^A-Z0-9]", "", text.upper())
    return text if 7 <= len(text) <= 11 else ""

def get_vehicle_type(plate):
    return VEHICLE_DB.get(plate, {"type": "Visitor"})["type"]

def student_time_allowed():
    hour = datetime.now().hour
    return STUDENT_START <= hour < STUDENT_END

def ensure_files():
    os.makedirs(SNAP_DIR, exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            csv.writer(f).writerow(
                ["timestamp", "plate", "type", "confidence", "snapshot"]
            )

# ================= MAIN LOOP =================
def main():
    global latest_frame, latest_detection, gate_state, alerts

    ensure_files()

    # ---------- CAMERA INIT (STABLE) ----------
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)
    # cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    # Force exposure / brightness (FIX BLACK SCREEN)
    # cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
    # cap.set(cv2.CAP_PROP_EXPOSURE, -5)
    # cap.set(cv2.CAP_PROP_BRIGHTNESS, 150)
    # cap.set(cv2.CAP_PROP_CONTRAST, 50)

    time.sleep(2)  # camera warm-up

    if not cap.isOpened():
        print("❌ Camera not accessible")
        return

    print("✅ OFFLINE ANPR STARTED (CAMPUS MODE)")

    # ---------- MAIN LOOP ----------
    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        display_frame = frame.copy()

        # ---------- YOLO DETECTION ----------
        results = model(frame, conf=CONF_THRESHOLD, verbose=False)

        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])

                plate_crop = frame[y1:y2, x1:x2]
                if plate_crop.size == 0:
                    continue

                ocr = reader.readtext(plate_crop)
                if not ocr:
                    continue

                plate = clean_plate(ocr[0][1])
                if not plate:
                    continue

                confidence = int(box.conf[0] * 100)
                vehicle_type = get_vehicle_type(plate)
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                snap_name = f"{plate}_{int(time.time())}.jpg"
                cv2.imwrite(os.path.join(SNAP_DIR, snap_name), frame)

                # ---------- DECISION LOGIC ----------
                if vehicle_type == "Blacklist":
                    status = "BLOCK"
                    reason = "🚨 Blacklisted Vehicle"
                    color = RED
                    alerts.append(f"{ts} ALERT: Blacklisted {plate}")

                elif vehicle_type == "Student":
                    if student_time_allowed():
                        status = "ALLOW"
                        reason = "Student – Allowed Time"
                        color = GREEN
                    else:
                        status = "BLOCK"
                        reason = "⏱ Student Outside Allowed Time"
                        color = RED
                        alerts.append(f"{ts} ALERT: Student late {plate}")

                elif vehicle_type == "Faculty":
                    status = "ALLOW"
                    reason = "Faculty Access"
                    color = GREEN

                else:
                    status = "ALLOW"
                    reason = "Visitor Logged"
                    color = YELLOW

                # ---------- DRAW BOUNDING BOX ----------
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 3)

                cv2.rectangle(
                    display_frame,
                    (x1, y1 - 30),
                    (x2, y1),
                    color,
                    -1
                )

                cv2.putText(
                    display_frame,
                    f"{plate} | {status} ({confidence}%)",
                    (x1 + 6, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    2
                )

                # ---------- UPDATE GLOBAL STATE ----------
                latest_detection.clear()
                latest_detection.update({
                    "timestamp": ts,
                    "plate": plate,
                    "type": vehicle_type,
                    "confidence": confidence,
                    "snapshot": snap_name
                })

                gate_state.update({
                    "status": status,
                    "reason": reason,
                    "updated": ts
                })

                with open(LOG_FILE, "a", newline="") as f:
                    csv.writer(f).writerow([
                        ts, plate, vehicle_type, confidence, snap_name
                    ])

                time.sleep(1.5)

        latest_frame = display_frame.copy()
        time.sleep(0.03)
