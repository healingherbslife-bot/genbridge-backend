"""
GenBridge Backend API — Flask Server
Routes:
  POST /api/auth/login
  POST /api/auth/logout
  GET  /api/auth/me

  GET/POST   /api/users
  GET/PUT    /api/users/<id>

  GET/POST   /api/trainers
  GET/PUT    /api/trainers/<id>

  GET/POST   /api/workshops
  GET/PUT    /api/workshops/<id>
  DELETE     /api/workshops/<id>

  GET/POST   /api/bookings
  GET/PUT    /api/bookings/<id>

  GET/POST   /api/invoices
  GET        /api/invoices/<id>/pdf
  PUT        /api/invoices/<id>

  GET        /api/dashboard
  GET        /api/revenue
"""

import os, json, uuid
from datetime import datetime, date
from flask import Flask, request, jsonify, g, send_file, Response
import io

from db import query, init_db
from auth import require_auth, generate_token
from werkzeug.security import generate_password_hash, check_password_hash
from pdf_generator import generate_invoice_pdf

app = Flask(__name__, static_folder="public", static_url_path="")

# ── CORS (allow your Netlify domain + localhost) ───────────────────────────────
ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5500,http://127.0.0.1:5500,https://genbridge.netlify.app"
).split(",")

@app.after_request
def add_cors(response):
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_ORIGINS or "*" in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"]  = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

@app.route("/api/<path:p>", methods=["OPTIONS"])
def options_handler(p):
    return jsonify({}), 200

# ── Init DB on startup ────────────────────────────────────────────────────────
with app.app_context():
    init_db()

# ═══════════════════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    user = query("SELECT * FROM users WHERE email=%s AND is_active=1", (email,), fetchone=True)
    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    token = generate_token(user["id"], user["role"], user["name"], user["email"])
    return jsonify({
        "token": token,
        "user": {
            "id":    user["id"],
            "name":  user["name"],
            "email": user["email"],
            "role":  user["role"],
            "avatar_url": user.get("avatar_url"),
        }
    })


@app.route("/api/auth/me", methods=["GET"])
@require_auth()
def me():
    user = query("SELECT id,name,email,role,avatar_url,created_at FROM users WHERE id=%s",
                 (g.user_id,), fetchone=True)
    return jsonify(user)


# ═══════════════════════════════════════════════════════════════════════════════
# USERS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/users", methods=["GET"])
@require_auth(roles=["admin"])
def list_users():
    users = query("SELECT id,name,email,role,is_active,created_at FROM users ORDER BY created_at DESC", fetchall=True)
    return jsonify(users)


@app.route("/api/users", methods=["POST"])
@require_auth(roles=["admin"])
def create_user():
    d = request.get_json() or {}
    required = ["email","password","name","role"]
    if not all(d.get(k) for k in required):
        return jsonify({"error": f"Required: {required}"}), 400
    existing = query("SELECT id FROM users WHERE email=%s", (d["email"],), fetchone=True)
    if existing:
        return jsonify({"error": "Email already registered"}), 409
    uid = query(
        "INSERT INTO users (email,password,name,role) VALUES (%s,%s,%s,%s)",
        (d["email"].lower(), generate_password_hash(d["password"]), d["name"], d["role"]),
        commit=True)
    return jsonify({"id": uid, "message": "User created"}), 201


@app.route("/api/users/<int:uid>", methods=["PUT"])
@require_auth(roles=["admin"])
def update_user(uid):
    d = request.get_json() or {}
    fields, vals = [], []
    for col in ["name","role","is_active","avatar_url"]:
        if col in d:
            fields.append(f"{col}=%s")
            vals.append(d[col])
    if "password" in d and d["password"]:
        fields.append("password=%s")
        vals.append(generate_password_hash(d["password"]))
    if not fields:
        return jsonify({"error": "Nothing to update"}), 400
    vals.append(uid)
    query(f"UPDATE users SET {','.join(fields)} WHERE id=%s", vals, commit=True)
    return jsonify({"message": "Updated"})


# ═══════════════════════════════════════════════════════════════════════════════
# TRAINERS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/trainers", methods=["GET"])
@require_auth()
def list_trainers():
    rows = query("""
        SELECT t.*, u.name, u.email, u.avatar_url as user_avatar
        FROM trainers t JOIN users u ON t.user_id=u.id
        ORDER BY t.rating DESC
    """, fetchall=True)
    for r in rows:
        if r.get("specialisations"):
            try: r["specialisations"] = json.loads(r["specialisations"])
            except: pass
    return jsonify(rows)


@app.route("/api/trainers", methods=["POST"])
@require_auth(roles=["admin"])
def create_trainer():
    d = request.get_json() or {}
    if not d.get("user_id"):
        return jsonify({"error": "user_id required"}), 400
    specs = json.dumps(d.get("specialisations", []))
    tid = query("""INSERT INTO trainers (user_id,bio,specialisations,qualifications,linkedin_url,photo_url)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (d["user_id"], d.get("bio",""), specs,
                 d.get("qualifications",""), d.get("linkedin_url",""), d.get("photo_url","")),
                commit=True)
    return jsonify({"id": tid, "message": "Trainer profile created"}), 201


@app.route("/api/trainers/<int:tid>", methods=["GET"])
@require_auth()
def get_trainer(tid):
    t = query("""SELECT t.*, u.name, u.email FROM trainers t JOIN users u ON t.user_id=u.id WHERE t.id=%s""",
              (tid,), fetchone=True)
    if not t:
        return jsonify({"error": "Not found"}), 404
    if t.get("specialisations"):
        try: t["specialisations"] = json.loads(t["specialisations"])
        except: pass
    return jsonify(t)


@app.route("/api/trainers/<int:tid>", methods=["PUT"])
@require_auth(roles=["admin","trainer"])
def update_trainer(tid):
    d = request.get_json() or {}
    fields, vals = [], []
    for col in ["bio","qualifications","linkedin_url","photo_url","is_available"]:
        if col in d:
            fields.append(f"{col}=%s")
            vals.append(d[col])
    if "specialisations" in d:
        fields.append("specialisations=%s")
        vals.append(json.dumps(d["specialisations"]))
    if not fields:
        return jsonify({"error": "Nothing to update"}), 400
    vals.append(tid)
    query(f"UPDATE trainers SET {','.join(fields)} WHERE id=%s", vals, commit=True)
    return jsonify({"message": "Updated"})


# ═══════════════════════════════════════════════════════════════════════════════
# PROGRAMMES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/programmes", methods=["GET"])
def list_programmes():
    rows = query("SELECT * FROM programmes WHERE is_active=1 ORDER BY code", fetchall=True)
    return jsonify(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# WORKSHOPS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/workshops", methods=["GET"])
@require_auth()
def list_workshops():
    month = request.args.get("month")           # YYYY-MM
    status = request.args.get("status")

    sql = """
        SELECT w.*, p.name as programme_name, p.code as programme_code,
               p.accent_color, t.id as trainer_profile_id,
               u.name as trainer_name,
               (SELECT COUNT(*) FROM bookings b WHERE b.workshop_id=w.id AND b.status!='cancelled') as booked_pax
        FROM workshops w
        LEFT JOIN programmes p ON w.programme_id=p.id
        LEFT JOIN trainers t ON w.trainer_id=t.id
        LEFT JOIN users u ON t.user_id=u.id
    """
    wheres, params = [], []
    if month:
        wheres.append("strftime('%Y-%m', w.start_datetime)=%s")
        params.append(month)
    if status:
        wheres.append("w.status=%s")
        params.append(status)
    if wheres:
        sql += " WHERE " + " AND ".join(wheres)
    sql += " ORDER BY w.start_datetime ASC"
    return jsonify(query(sql, params, fetchall=True))


@app.route("/api/workshops", methods=["POST"])
@require_auth(roles=["admin","hr_manager"])
def create_workshop():
    d = request.get_json() or {}
    required = ["programme_id","title","start_datetime","end_datetime"]
    if not all(d.get(k) for k in required):
        return jsonify({"error": f"Required fields: {required}"}), 400
    wid = query("""INSERT INTO workshops
        (programme_id,trainer_id,title,start_datetime,end_datetime,venue,max_capacity,notes,created_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (d["programme_id"], d.get("trainer_id"), d["title"],
         d["start_datetime"], d["end_datetime"],
         d.get("venue",""), d.get("max_capacity",20), d.get("notes",""), g.user_id),
        commit=True)
    return jsonify({"id": wid, "message": "Workshop created"}), 201


@app.route("/api/workshops/<int:wid>", methods=["GET"])
@require_auth()
def get_workshop(wid):
    w = query("""
        SELECT w.*, p.name as programme_name, p.code, p.accent_color,
               u.name as trainer_name
        FROM workshops w
        LEFT JOIN programmes p ON w.programme_id=p.id
        LEFT JOIN trainers t ON w.trainer_id=t.id
        LEFT JOIN users u ON t.user_id=u.id
        WHERE w.id=%s
    """, (wid,), fetchone=True)
    if not w:
        return jsonify({"error": "Not found"}), 404
    bookings = query("SELECT * FROM bookings WHERE workshop_id=%s ORDER BY created_at DESC", (wid,), fetchall=True)
    w["bookings"] = bookings
    return jsonify(w)


@app.route("/api/workshops/<int:wid>", methods=["PUT"])
@require_auth(roles=["admin","hr_manager"])
def update_workshop(wid):
    d = request.get_json() or {}
    fields, vals = [], []
    for col in ["trainer_id","title","start_datetime","end_datetime","venue","max_capacity","status","notes"]:
        if col in d:
            fields.append(f"{col}=%s")
            vals.append(d[col])
    if not fields:
        return jsonify({"error": "Nothing to update"}), 400
    vals.append(wid)
    query(f"UPDATE workshops SET {','.join(fields)} WHERE id=%s", vals, commit=True)
    return jsonify({"message": "Updated"})


@app.route("/api/workshops/<int:wid>", methods=["DELETE"])
@require_auth(roles=["admin"])
def delete_workshop(wid):
    query("UPDATE workshops SET status='cancelled' WHERE id=%s", (wid,), commit=True)
    return jsonify({"message": "Workshop cancelled"})


# ── Calendar endpoint (grouped by date) ────────────────────────────────────────
@app.route("/api/workshops/calendar", methods=["GET"])
@require_auth()
def calendar():
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    rows = query("""
        SELECT w.id, w.title, w.start_datetime, w.end_datetime, w.status,
               w.max_capacity, w.venue,
               p.name as programme_name, p.code, p.accent_color,
               u.name as trainer_name
        FROM workshops w
        LEFT JOIN programmes p ON w.programme_id=p.id
        LEFT JOIN trainers t ON w.trainer_id=t.id
        LEFT JOIN users u ON t.user_id=u.id
        WHERE strftime('%Y-%m', w.start_datetime)=%s
        ORDER BY w.start_datetime
    """, (month,), fetchall=True)

    # Group by date
    calendar = {}
    for row in rows:
        day = row["start_datetime"][:10]
        calendar.setdefault(day, []).append(row)
    return jsonify(calendar)


# ═══════════════════════════════════════════════════════════════════════════════
# BOOKINGS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/bookings", methods=["GET"])
@require_auth()
def list_bookings():
    rows = query("""
        SELECT b.*, w.title as workshop_title, w.start_datetime,
               p.name as programme_name, p.code
        FROM bookings b
        LEFT JOIN workshops w ON b.workshop_id=w.id
        LEFT JOIN programmes p ON w.programme_id=p.id
        ORDER BY b.created_at DESC LIMIT 100
    """, fetchall=True)
    return jsonify(rows)


@app.route("/api/bookings", methods=["POST"])
@require_auth(roles=["admin","hr_manager"])
def create_booking():
    d = request.get_json() or {}
    required = ["workshop_id","client_name","client_email","pax_count"]
    if not all(d.get(k) for k in required):
        return jsonify({"error": f"Required: {required}"}), 400

    # Calculate total from programme price
    ws = query("""SELECT w.*,p.price_per_pax FROM workshops w
                  JOIN programmes p ON w.programme_id=p.id WHERE w.id=%s""",
               (d["workshop_id"],), fetchone=True)
    if not ws:
        return jsonify({"error": "Workshop not found"}), 404

    pax   = int(d["pax_count"])
    total = pax * (ws["price_per_pax"] or 0)
    bid = query("""INSERT INTO bookings
        (workshop_id,client_name,client_email,client_company,client_phone,pax_count,total_amount,notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (d["workshop_id"], d["client_name"], d["client_email"],
         d.get("client_company",""), d.get("client_phone",""),
         pax, total, d.get("notes","")),
        commit=True)

    # Auto-create invoice
    inv_num = f"INV-{datetime.now().year}-{1000+bid}"
    due     = datetime.now().date()
    due_str = f"{due.year}-{due.month:02d}-{due.day+14:02d}"   # +14 days
    inv_id  = query("""INSERT INTO invoices
        (invoice_number,booking_id,subtotal,tax_amount,total_amount,due_date)
        VALUES (%s,%s,%s,%s,%s,%s)""",
        (inv_num, bid, total, 0, total, due_str), commit=True)

    return jsonify({"booking_id": bid, "invoice_id": inv_id, "invoice_number": inv_num,
                    "total_amount": total}), 201


@app.route("/api/bookings/<int:bid>", methods=["PUT"])
@require_auth(roles=["admin","hr_manager"])
def update_booking(bid):
    d = request.get_json() or {}
    fields, vals = [], []
    for col in ["status","notes","pax_count"]:
        if col in d:
            fields.append(f"{col}=%s")
            vals.append(d[col])
    if not fields:
        return jsonify({"error": "Nothing to update"}), 400
    vals.append(bid)
    query(f"UPDATE bookings SET {','.join(fields)} WHERE id=%s", vals, commit=True)
    return jsonify({"message": "Updated"})


# ═══════════════════════════════════════════════════════════════════════════════
# INVOICES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/invoices", methods=["GET"])
@require_auth()
def list_invoices():
    rows = query("""
        SELECT i.*, b.client_name, b.client_email, b.client_company,
               w.title as workshop_title, p.name as programme_name, p.code
        FROM invoices i
        LEFT JOIN bookings b ON i.booking_id=b.id
        LEFT JOIN workshops w ON b.workshop_id=w.id
        LEFT JOIN programmes p ON w.programme_id=p.id
        ORDER BY i.created_at DESC LIMIT 100
    """, fetchall=True)
    return jsonify(rows)


@app.route("/api/invoices/<int:iid>", methods=["GET"])
@require_auth()
def get_invoice(iid):
    inv = query("SELECT * FROM invoices WHERE id=%s", (iid,), fetchone=True)
    if not inv:
        return jsonify({"error": "Not found"}), 404
    booking  = query("SELECT * FROM bookings WHERE id=%s", (inv["booking_id"],), fetchone=True)
    workshop = None
    prog     = None
    if booking:
        workshop = query("SELECT * FROM workshops WHERE id=%s", (booking["workshop_id"],), fetchone=True)
        if workshop:
            prog = query("SELECT * FROM programmes WHERE id=%s", (workshop["programme_id"],), fetchone=True)
    return jsonify({"invoice": inv, "booking": booking, "workshop": workshop, "programme": prog})


@app.route("/api/invoices/<int:iid>/pdf", methods=["GET"])
@require_auth()
def download_invoice_pdf(iid):
    inv = query("SELECT * FROM invoices WHERE id=%s", (iid,), fetchone=True)
    if not inv:
        return jsonify({"error": "Not found"}), 404
    booking  = query("SELECT * FROM bookings WHERE id=%s", (inv["booking_id"],), fetchone=True)
    workshop = query("SELECT * FROM workshops WHERE id=%s", (booking["workshop_id"],), fetchone=True) if booking else None
    prog     = query("SELECT * FROM programmes WHERE id=%s", (workshop["programme_id"],), fetchone=True) if workshop else None

    pdf_bytes = generate_invoice_pdf(inv, booking or {}, workshop or {}, prog or {})
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="invoice-{inv["invoice_number"]}.pdf"'}
    )


@app.route("/api/invoices/<int:iid>", methods=["PUT"])
@require_auth(roles=["admin","hr_manager"])
def update_invoice(iid):
    d = request.get_json() or {}
    fields, vals = [], []
    for col in ["status","paid_date","notes","due_date"]:
        if col in d:
            fields.append(f"{col}=%s")
            vals.append(d[col])
    if not fields:
        return jsonify({"error": "Nothing to update"}), 400

    # Log revenue when marking as paid
    if d.get("status") == "paid":
        inv = query("SELECT * FROM invoices WHERE id=%s", (iid,), fetchone=True)
        if inv and inv.get("status") != "paid":
            booking  = query("SELECT * FROM bookings WHERE id=%s", (inv["booking_id"],), fetchone=True)
            workshop = query("SELECT * FROM workshops WHERE id=%s", (booking["workshop_id"],), fetchone=True) if booking else None
            prog_id  = workshop["programme_id"] if workshop else None
            query("INSERT INTO revenue_log (invoice_id,amount,programme_id) VALUES (%s,%s,%s)",
                  (iid, inv["total_amount"], prog_id), commit=True)

    vals.append(iid)
    query(f"UPDATE invoices SET {','.join(fields)} WHERE id=%s", vals, commit=True)
    return jsonify({"message": "Invoice updated"})


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD & REVENUE
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/dashboard", methods=["GET"])
@require_auth()
def dashboard():
    # KPI cards
    total_revenue = query(
        "SELECT COALESCE(SUM(amount),0) as total FROM revenue_log", fetchone=True)["total"]
    total_workshops = query(
        "SELECT COUNT(*) as c FROM workshops WHERE status!='cancelled'", fetchone=True)["c"]
    total_bookings = query(
        "SELECT COUNT(*) as c FROM bookings WHERE status='confirmed'", fetchone=True)["c"]
    total_trainers = query(
        "SELECT COUNT(*) as c FROM trainers WHERE is_available=1", fetchone=True)["c"]

    unpaid_invoices = query(
        "SELECT COUNT(*) as c, COALESCE(SUM(total_amount),0) as amt FROM invoices WHERE status='unpaid'",
        fetchone=True)
    upcoming = query("""
        SELECT w.id, w.title, w.start_datetime, w.venue, w.status,
               p.name as programme_name, p.accent_color, p.code,
               u.name as trainer_name
        FROM workshops w
        LEFT JOIN programmes p ON w.programme_id=p.id
        LEFT JOIN trainers t ON w.trainer_id=t.id
        LEFT JOIN users u ON t.user_id=u.id
        WHERE w.start_datetime >= datetime('now') AND w.status!='cancelled'
        ORDER BY w.start_datetime LIMIT 5
    """, fetchall=True)

    recent_bookings = query("""
        SELECT b.*, w.title as workshop_title, p.code
        FROM bookings b
        JOIN workshops w ON b.workshop_id=w.id
        JOIN programmes p ON w.programme_id=p.id
        ORDER BY b.created_at DESC LIMIT 6
    """, fetchall=True)

    recent_invoices = query("""
        SELECT i.*, b.client_name, b.client_company
        FROM invoices i JOIN bookings b ON i.booking_id=b.id
        ORDER BY i.created_at DESC LIMIT 5
    """, fetchall=True)

    return jsonify({
        "kpis": {
            "total_revenue":    total_revenue,
            "total_workshops":  total_workshops,
            "total_bookings":   total_bookings,
            "total_trainers":   total_trainers,
            "unpaid_invoices":  unpaid_invoices["c"],
            "unpaid_amount":    unpaid_invoices["amt"],
        },
        "upcoming_workshops": upcoming,
        "recent_bookings":    recent_bookings,
        "recent_invoices":    recent_invoices,
    })


@app.route("/api/revenue", methods=["GET"])
@require_auth(roles=["admin","hr_manager"])
def revenue_data():
    # Monthly revenue for last 12 months
    monthly = query("""
        SELECT strftime('%Y-%m', log_date) as month,
               SUM(amount) as total
        FROM revenue_log
        GROUP BY strftime('%Y-%m', log_date)
        ORDER BY month DESC LIMIT 12
    """, fetchall=True)
    monthly.reverse()

    # Revenue by programme
    by_prog = query("""
        SELECT p.name, p.code, p.accent_color,
               COUNT(*) as sessions,
               SUM(rl.amount) as total
        FROM revenue_log rl
        JOIN programmes p ON rl.programme_id=p.id
        GROUP BY p.id ORDER BY total DESC
    """, fetchall=True)

    # Invoice status breakdown
    inv_status = query("""
        SELECT status, COUNT(*) as count, COALESCE(SUM(total_amount),0) as amount
        FROM invoices GROUP BY status
    """, fetchall=True)

    return jsonify({
        "monthly":        monthly,
        "by_programme":   by_prog,
        "invoice_status": inv_status,
    })


# ── Health check ───────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "service": "GenBridge API", "version": "1.0.0"})


# ── Serve admin SPA ───────────────────────────────────────────────────────────
@app.route("/admin")
@app.route("/admin/")
def admin_index():
    return app.send_static_file("admin/index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"🚀 GenBridge API running on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
