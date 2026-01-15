import cv2
import time
import csv
import os
import requests
from datetime import datetime
from config import *
import re

DUPLICATE_TIMEOUT = 10  # seconds
PLATE_PADDING = 10  # pixels around plate crop

latest_detection = {}
latest_frame = None

def is_valid_plate(plate):
    """
    Validates Indian vehicle number plates
    """
    pattern = r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}$"
    return re.match(pattern, plate) is not None


def main():
    global latest_frame

    print("🚀 ANPR started")

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("❌ Camera not accessible")
        return

    os.makedirs("snapshots", exist_ok=True)

    # warmup
    for _ in range(10):
        cap.read()

    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            csv.writer(f).writerow(
                ["timestamp", "plate", "blacklist", "confidence", "snapshot"]
            )

    last_api_call = 0
    last_results = []
    seen_plates = set()
    last_seen = {}


    while True:
        ret, frame = cap.read()
        if not ret:
            break

        display = frame.copy()
        now = time.time()

        # ---- API CALL ----
        if now - last_api_call > API_INTERVAL:
            last_api_call = now
            cv2.imwrite("frame.jpg", frame)

            try:
                r = requests.post(
                    API_URL,
                    files={"upload": open("frame.jpg", "rb")},
                    data={"regions": ["in"], "detect_blur": True},
                    headers={"Authorization": f"Token {API_TOKEN}"},
                    timeout=5
                )
                last_results = r.json().get("results", [])
            except:
                pass

        # ---- PROCESS RESULTS ----
        for res in last_results:
            plate = res["plate"].upper()
            current_time = time.time()

            # ⏱️ Duplicate suppression
            if plate in last_seen:
                if current_time - last_seen[plate] < DUPLICATE_TIMEOUT:
                    continue  # skip duplicate detection

            last_seen[plate] = current_time

            # 🚫 Reject invalid / noisy plates
            if not is_valid_plate(plate):
                continue

            confidence = int(res.get("score", 0) * 100)
            box = res["box"]
            x1, y1, x2, y2 = box["xmin"], box["ymin"], box["xmax"], box["ymax"]

            alert = "YES" if plate in BLACKLIST else "NO"

            if plate not in seen_plates:
                seen_plates.add(plate)

                # snapshot_name = f"{plate}_{int(time.time())}.jpg"
                # snapshot_path = os.path.join("snapshots", snapshot_name)
                # cv2.imwrite(snapshot_path, frame)

                # 🎯 Crop ONLY plate region
                h, w, _ = frame.shape

                x1p = max(0, x1 - PLATE_PADDING)
                y1p = max(0, y1 - PLATE_PADDING)
                x2p = min(w, x2 + PLATE_PADDING)
                y2p = min(h, y2 + PLATE_PADDING)

                plate_crop = frame[y1p:y2p, x1p:x2p]

                snapshot_name = f"{plate}_{int(time.time())}.jpg"
                snapshot_path = os.path.join("snapshots", snapshot_name)

                # Save cropped plate only
                cv2.imwrite(snapshot_path, plate_crop)

                latest_detection.clear()
                latest_detection.update({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "plate": plate,
                    "blacklist": alert,
                    "confidence": confidence,
                    "snapshot": snapshot_name
                })

                with open(LOG_FILE, "a", newline="") as f:
                    csv.writer(f).writerow([
                        latest_detection["timestamp"],
                        plate,
                        alert,
                        confidence,
                        snapshot_name
                    ])

            color = (0, 0, 255) if alert == "YES" else (0, 255, 0)
            cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
            cv2.putText(display, plate, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

        cv2.putText(display, "MODE: DAYLIGHT", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        latest_frame = display.copy()

        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    print("🛑 ANPR stopped")
