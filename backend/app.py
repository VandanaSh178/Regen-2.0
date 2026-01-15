from flask import Flask, jsonify, render_template, Response, send_from_directory
import threading, time, cv2, csv, os
import anpr

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder="templates")

@app.route("/")
def dashboard():
    return render_template("index.html")

@app.route("/latest")
def latest():
    return jsonify(anpr.latest_detection or {"status": "waiting"})

# ---------------- HISTORY ----------------
@app.route("/history")
def history():
    data = []
    log_path = os.path.join(BASE_DIR, "logs.csv")

    if not os.path.exists(log_path):
        return jsonify(data)

    with open(log_path, newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

        for row in rows[1:]:
            data.append({
                "timestamp": row[0] if len(row) > 0 else "",
                "plate": row[1] if len(row) > 1 else "",
                "blacklist": row[2] if len(row) > 2 else "",
                "confidence": row[3] if len(row) > 3 else "N/A",
                "snapshot": row[4] if len(row) > 4 else ""
            })

    return jsonify(data)

# ---------------- ANALYTICS ----------------
@app.route("/stats")
def stats():
    log_path = os.path.join(BASE_DIR, "logs.csv")

    total = 0
    unique = set()
    blacklist_count = 0

    if os.path.exists(log_path):
        with open(log_path, newline="") as f:
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

# ---------------- SNAPSHOTS ----------------
@app.route("/snapshots/<filename>")
def snapshots(filename):
    return send_from_directory(
        os.path.join(BASE_DIR, "snapshots"),
        filename
    )

# ---------------- VIDEO STREAM ----------------
def gen_frames():
    while True:
        if anpr.latest_frame is None:
            time.sleep(0.03)   # 🔥 prevent CPU burn
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
    threading.Thread(target=start_anpr, daemon=True).start()
    print("🚀 Open dashboard at http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
