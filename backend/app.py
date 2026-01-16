from flask import Flask, jsonify, render_template, Response, send_from_directory, request
import threading, time, cv2, csv, os
import anpr
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "logs.csv")
SNAP_DIR = os.path.join(BASE_DIR, "snapshots")

app = Flask(__name__, template_folder="templates")

# ---------------- DASHBOARD ----------------
@app.route("/")
def dashboard():
    return render_template("index.html")

# ---------------- LIVE DETECTION ----------------
@app.route("/latest")
def latest():
    return jsonify(anpr.latest_detection or {"status": "waiting"})

# ---------------- HISTORY ----------------
@app.route("/history")
def history():
    window = request.args.get("window", "all")
    now = datetime.now()

    if window == "5m":
        cutoff = now - timedelta(minutes=5)
    elif window == "1h":
        cutoff = now - timedelta(hours=1)
    elif window == "today":
        cutoff = datetime(now.year, now.month, now.day)
    else:
        cutoff = None

    data = []

    if not os.path.exists(LOG_FILE):
        return jsonify(data)

    with open(LOG_FILE, newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            ts_raw = row.get("timestamp", "")
            if not ts_raw:
                continue

            try:
                ts = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    ts = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S.%f")
                except ValueError:
                    continue

            if cutoff and ts < cutoff:
                continue

            data.append({
                "timestamp": ts_raw,
                "plate": row.get("plate", ""),
                "blacklist": row.get("blacklist", ""),
                "confidence": row.get("confidence", "N/A"),
                "snapshot": row.get("snapshot", "")
            })

    return jsonify(data)

# ---------------- ANALYTICS ----------------
@app.route("/stats")
def stats():
    total = 0
    unique = set()
    blacklist_count = 0

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)

            for r in rows[1:]:
                if len(r) < 3:
                    continue
                total += 1
                unique.add(r[1])
                if r[2] == "YES":
                    blacklist_count += 1

    return jsonify({
        "total": total,
        "unique": len(unique),
        "blacklist": blacklist_count,
        "api": getattr(anpr, "api_status", "OK")
    })

# ---------------- INCIDENT TIMELINE ----------------
@app.route("/timeline")
def timeline():
    events = []

    if not os.path.exists(LOG_FILE):
        return jsonify(events)

    with open(LOG_FILE, newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            if row.get("blacklist") == "YES":
                plate = row.get("plate", "")
                ts = row.get("timestamp", "")
                snapshot = row.get("snapshot", "")

                events.append({
                    "time": ts,
                    "event": f"🚫 Blacklisted vehicle detected ({plate})",
                    "snapshot": snapshot
                })
                events.append({
                    "time": ts,
                    "event": "📸 Snapshot captured",
                    "snapshot": snapshot
                })
                events.append({
                    "time": ts,
                    "event": "🔔 Alert triggered",
                    "snapshot": snapshot
                })

    return jsonify(events[-20:])

# ---------------- SNAPSHOTS ----------------
@app.route("/snapshots/<filename>")
def snapshots(filename):
    return send_from_directory(SNAP_DIR, filename)

# ---------------- VIDEO STREAM ----------------
def gen_frames():
    while True:
        if anpr.latest_frame is None:
            time.sleep(0.03)
            continue

        ret, buffer = cv2.imencode(".jpg", anpr.latest_frame)
        if not ret:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" +
            buffer.tobytes() + b"\r\n"
        )

@app.route("/video_feed")
def video_feed():
    return Response(
        gen_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

# ---------------- START ANPR THREAD ----------------
def start_anpr():
    time.sleep(1)
    anpr.main()

if __name__ == "__main__":
    os.makedirs(SNAP_DIR, exist_ok=True)
    threading.Thread(target=start_anpr, daemon=True).start()
    print("🚀 Open dashboard at http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
