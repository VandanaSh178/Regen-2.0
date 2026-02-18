from flask import (
    Flask, jsonify, render_template, Response,
    send_from_directory, request, session, redirect
)
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import threading, time, cv2, csv, os, importlib, io

# Import custom modules
import anpr
import vehicle_db
from gate_controller import gate_manager

# ================== 1. APP INIT ==================
app = Flask(__name__, template_folder="../templates", static_folder="../static")
app.secret_key = "nit-manipur-astra-security"

# ================== 2. ADMIN CREDENTIALS ==================
ADMIN_USER = "admin"
ADMIN_PASSWORD_HASH = generate_password_hash("nitmanipur@2026")

# ================== 3. AUTH DECORATOR ==================
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return wrapper

# about
@app.route("/about")
def about():
    """Serves the technical specifications and project overview"""
    return render_template("about.html")

# ================== 4. CORE PUBLIC ROUTES ==================
# ================== 4. CORE PUBLIC ROUTES ==================

@app.route("/")
def hero():
    """Serves the professional Astra Hero/Intro Page"""
    return render_template("hero.html")

@app.route("/dashboard")
def home():
    """Serves the professional Astra Dashboard"""
    # Note: This was originally your "/" route. 
    # We moved it so the Hero page can play first.
    return render_template("index.html")

# @app.route("/")
# def home():
#     """Serves the professional Astra Dashboard"""
#     return render_template("index.html")

@app.route("/video_feed")
def video_feed():
    """Streams the camera feed to the dashboard HUD"""
    def gen():
        while True:
            if anpr.latest_frame is None:
                time.sleep(0.1)
                continue
            _, buf = cv2.imencode(".jpg", anpr.latest_frame)
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/gate_status")
def gate_status():
    try:
        raw_data = anpr.latest_detection or {}
        plate = raw_data.get("plate", "----")
        confidence = raw_data.get("confidence", 0)
        status, v_type, reason = gate_manager.evaluate_access(plate, confidence)

        return jsonify({
            "plate": plate,
            "type": v_type,
            "confidence": confidence,
            "status": status,
            "reason": reason
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/history")
def history():
    rows = []
    if os.path.exists("logs.csv"):
        with open("logs.csv", "r") as f:
            reader = csv.reader(f)
            next(reader, None)
            for r in list(reader):
                if len(r) < 4: continue
                rows.append({
                    "timestamp": r[0], 
                    "plate": r[1], 
                    "type": r[2], 
                    "confidence": r[3],
                    "snapshot": r[4] if len(r) > 4 else "" 
                })
    return jsonify(rows[::-1])

@app.route("/snapshots/<path:filename>")
def serve_snapshot(filename):
    return send_from_directory("snapshots", filename)

# ================== 5. ADMIN AUTH & LOGIC ==================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        data = request.json if request.is_json else request.form
        username = data.get("username")
        password = data.get("password")

        if username == ADMIN_USER and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session["admin"] = True
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "Invalid Credentials"}), 401
    return render_template("admin_login.html")

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/")

# ================== 6. DATABASE ACTIONS ==================

@app.route("/admin/get_vehicles")
@admin_required
def get_vehicles():
    vehicles = []
    for plate, info in vehicle_db.VEHICLE_DB.items():
        vehicles.append({
            "plate": plate,
            "owner": info.get("owner", "Unknown"),
            "type": info.get("type", "Visitor"),
            "dept": info.get("dept", "N/A")
        })
    return jsonify(vehicles)

def save_db_to_file():
    with open("vehicle_db.py", "w") as f:
        f.write(f"VEHICLE_DB = {vehicle_db.VEHICLE_DB}")
    importlib.reload(vehicle_db)

@app.route("/admin/add_vehicle", methods=["POST"])
@admin_required
def add_vehicle_api():
    data = request.json
    plate = data.get("plate", "").strip().upper()
    if not plate:
        return jsonify({"success": False, "error": "Plate required"}), 400
    
    vehicle_db.VEHICLE_DB[plate] = {
        "type": data.get("type", "Visitor"),
        "owner": data.get("owner", "Unknown"),
        "dept": data.get("dept", "N/A")
    }
    save_db_to_file()
    return jsonify({"success": True})



@app.route("/admin/delete_vehicle/<plate>", methods=["DELETE"])
@admin_required
def delete_vehicle(plate):
    plate = plate.upper().strip()
    if plate in vehicle_db.VEHICLE_DB:
        del vehicle_db.VEHICLE_DB[plate]
        save_db_to_file()
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Vehicle not found"}), 404

@app.route("/stats")
def get_stats():
    total, students, faculty, official = 0, 0, 0, 0
    if os.path.exists("logs.csv"):
        with open("logs.csv", "r") as f:
            reader = list(csv.reader(f))
            for r in reader[1:]:
                if len(r) < 3: continue
                total += 1
                cat = r[2]
                if cat == "Student": students += 1
                elif cat == "Faculty": faculty += 1
                else: official += 1
    return jsonify({"total": total, "students": students, "faculty": faculty, "official": official})

@app.route("/admin/export_excel")
@admin_required
def export_excel():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Timestamp', 'License Plate', 'Vehicle Category', 'Confidence %', 'Entry Status'])
    
    if os.path.exists("logs.csv"):
        with open("logs.csv", "r") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                status = "DENIED" if row[2] == "Blacklist" else "AUTHORIZED"
                writer.writerow([row[0], row[1], row[2], f"{row[3]}%", status])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=Astra_Security_Report_2026.csv"}
    )

# ================== 7. BACKGROUND THREAD & MAIN ==================

def start_anpr():
    print("🚀 Astra AI Core Initializing...")
    while True:
        try:
            anpr.main()
        except Exception as e:
            print(f"🔥 AI Core Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    if not os.path.exists("snapshots"):
        os.makedirs("snapshots")
    threading.Thread(target=start_anpr, daemon=True).start()
    print("✅ System Online at http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)