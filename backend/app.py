from flask import (
    Flask, jsonify, render_template, Response,
    send_from_directory, request, session, redirect
)
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import threading, time, cv2, csv, os, importlib, io

# Import custom modules
import anpr
import vehicle_db

# ================== 1. APP INIT ==================
app = Flask(__name__, template_folder="../templates")
app.secret_key = "nit-manipur-campuscar"

# ================== 2. ADMIN CREDENTIALS ==================
ADMIN_USER = "admin"
# Password is 'nitmanipur@2026'
ADMIN_PASSWORD_HASH = generate_password_hash("nitmanipur@2026")

# ================== 3. AUTH DECORATOR ==================
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return wrapper

# ================== 4. DATABASE & LOGIC ==================

def save_db_to_file():
    """Helper to physically save the VEHICLE_DB dictionary to vehicle_db.py"""
    with open("vehicle_db.py", "w") as f:
        f.write(f"VEHICLE_DB = {vehicle_db.VEHICLE_DB}")
    importlib.reload(vehicle_db)

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
    return jsonify({"success": False, "error": "Not found"}), 404

# ================== 5. REPORTING (PDF) ==================

@app.route("/admin/export_report")
@admin_required
def export_report():
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    elements.append(Paragraph("NIT Manipur - Campus Security Report", styles['Title']))
    elements.append(Paragraph(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    elements.append(Paragraph("<br/><br/>", styles['Normal']))
    
    data = [["Timestamp", "Plate", "Category", "Confidence"]]
    if os.path.exists("logs.csv"):
        with open("logs.csv", "r") as f:
            reader = list(csv.reader(f))
            for row in reader[-50:]: # Last 50 detections
                if len(row) >= 4:
                    data.append([row[0], row[1], row[2], f"{row[3]}%"])
    
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.cadetblue),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('GRID', (0,0), (-1,-1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.lightgrey])
    ]))
    elements.append(t)
    doc.build(elements)
    buf.seek(0)
    return Response(buf, mimetype='application/pdf', 
                    headers={'Content-Disposition': 'attachment;filename=Security_Report.pdf'})

# ================== 6. STREAMING & LOGS ==================

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/latest")
def latest():
    return jsonify(anpr.latest_detection or {})

@app.route("/history")
def history():
    rows = []
    if os.path.exists("logs.csv"):
        with open("logs.csv") as f:
            for r in list(csv.reader(f))[1:]:
                if len(r) < 5: continue
                rows.append({"timestamp": r[0], "plate": r[1], "type": r[2], "confidence": r[3], "snapshot": r[4]})
    return jsonify(rows)

@app.route("/video_feed")
def video_feed():
    def gen():
        while True:
            if anpr.latest_frame is None:
                time.sleep(0.1); continue
            _, buf = cv2.imencode(".jpg", anpr.latest_frame)
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/snapshots/<name>")
def snapshots(name):
    return send_from_directory("snapshots", name)

@app.route("/stats")
def stats():
    total, students, faculty = 0, 0, 0
    if os.path.exists("logs.csv"):
        with open("logs.csv") as f:
            reader = list(csv.reader(f))
            for r in reader[1:]:
                if len(r) < 3: continue
                total += 1
                if r[2] == "Student": students += 1
                elif r[2] == "Faculty": faculty += 1
    return jsonify({"total": total, "students": students, "faculty": faculty})

# ================== 7. AUTH & DASHBOARD ==================

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        data = request.json
        if data["username"] == ADMIN_USER and check_password_hash(ADMIN_PASSWORD_HASH, data["password"]):
            session["admin"] = True
            return jsonify({"success": True})
        return jsonify({"success": False}), 401
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/")

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html")

# ================== 8. ANPR THREAD ==================

def start_anpr():
    while True:
        try:
            anpr.main()
        except Exception as e:
            print("🔥 ANPR Error:", e)
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=start_anpr, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)