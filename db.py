"""
GenBridge Database Layer
- Uses SQLite locally / development
- Schema is 100% PostgreSQL (Neon) compatible — swap the connection string in .env
- To use Neon: pip install psycopg2-binary and set DATABASE_URL in .env
"""
import sqlite3
import os
import json
from datetime import datetime

DATABASE_PATH = os.environ.get("DATABASE_PATH", "genbridge.db")
DATABASE_URL  = os.environ.get("DATABASE_URL", "")   # Neon connection string when deployed

def get_connection():
    """Return a DB connection — SQLite locally, Neon/Postgres in production."""
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        try:
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(DATABASE_URL)
            conn.autocommit = False
            return conn, "postgres"
        except ImportError:
            pass
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn, "sqlite"


def query(sql, params=(), fetchone=False, fetchall=False, commit=False):
    """Execute a query and return results as plain dicts."""
    conn, dialect = get_connection()
    # Normalise placeholders: Neon uses %s, SQLite uses ?
    if dialect == "sqlite":
        sql = sql.replace("%s", "?")
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        if commit:
            conn.commit()
            return cur.lastrowid if dialect == "sqlite" else (cur.fetchone()[0] if cur.description else None)
        if fetchone:
            row = cur.fetchone()
            if row is None:
                return None
            if dialect == "sqlite":
                return dict(row)
            return dict(zip([d[0] for d in cur.description], row))
        if fetchall:
            rows = cur.fetchall()
            if dialect == "sqlite":
                return [dict(r) for r in rows]
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]
        return None
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist."""
    conn, dialect = get_connection()
    cur = conn.cursor()

    serial   = "INTEGER PRIMARY KEY AUTOINCREMENT" if dialect == "sqlite" else "SERIAL PRIMARY KEY"
    now_fn   = "datetime('now')"                   if dialect == "sqlite" else "NOW()"
    bool_t   = "INTEGER"                           if dialect == "sqlite" else "BOOLEAN"
    true_val = "1"                                 if dialect == "sqlite" else "TRUE"

    statements = [
        # ── Users (admin / trainer / hr_manager) ──────────────────────────
        f"""CREATE TABLE IF NOT EXISTS users (
            id          {serial},
            email       TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            name        TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'hr_manager',  -- admin | trainer | hr_manager
            avatar_url  TEXT,
            is_active   {bool_t} DEFAULT {true_val},
            created_at  TEXT DEFAULT ({now_fn})
        )""",

        # ── Trainer Profiles ───────────────────────────────────────────────
        f"""CREATE TABLE IF NOT EXISTS trainers (
            id              {serial},
            user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,
            bio             TEXT,
            specialisations TEXT,   -- JSON array of strings
            qualifications  TEXT,
            linkedin_url    TEXT,
            photo_url       TEXT,
            rating          REAL DEFAULT 5.0,
            sessions_count  INTEGER DEFAULT 0,
            is_available    {bool_t} DEFAULT {true_val},
            created_at      TEXT DEFAULT ({now_fn})
        )""",

        # ── Programmes catalogue ───────────────────────────────────────────
        f"""CREATE TABLE IF NOT EXISTS programmes (
            id          {serial},
            code        TEXT UNIQUE NOT NULL,   -- GB-01 … GB-06
            name        TEXT NOT NULL,
            description TEXT,
            duration    TEXT,
            format      TEXT,
            price_per_pax INTEGER,
            min_pax     INTEGER DEFAULT 10,
            max_pax     INTEGER DEFAULT 20,
            accent_color TEXT DEFAULT '#0D7377',
            is_active   {bool_t} DEFAULT {true_val}
        )""",

        # ── Workshops (scheduled instances) ───────────────────────────────
        f"""CREATE TABLE IF NOT EXISTS workshops (
            id              {serial},
            programme_id    INTEGER REFERENCES programmes(id),
            trainer_id      INTEGER REFERENCES trainers(id),
            title           TEXT NOT NULL,
            start_datetime  TEXT NOT NULL,
            end_datetime    TEXT NOT NULL,
            venue           TEXT,
            max_capacity    INTEGER DEFAULT 20,
            status          TEXT DEFAULT 'scheduled',  -- scheduled|confirmed|completed|cancelled
            notes           TEXT,
            created_by      INTEGER REFERENCES users(id),
            created_at      TEXT DEFAULT ({now_fn})
        )""",

        # ── Bookings ──────────────────────────────────────────────────────
        f"""CREATE TABLE IF NOT EXISTS bookings (
            id              {serial},
            workshop_id     INTEGER REFERENCES workshops(id),
            client_name     TEXT NOT NULL,
            client_email    TEXT NOT NULL,
            client_company  TEXT,
            client_phone    TEXT,
            pax_count       INTEGER DEFAULT 1,
            total_amount    INTEGER,    -- in LKR cents
            status          TEXT DEFAULT 'pending',  -- pending|confirmed|cancelled
            notes           TEXT,
            created_at      TEXT DEFAULT ({now_fn})
        )""",

        # ── Invoices ──────────────────────────────────────────────────────
        f"""CREATE TABLE IF NOT EXISTS invoices (
            id              {serial},
            invoice_number  TEXT UNIQUE NOT NULL,
            booking_id      INTEGER REFERENCES bookings(id),
            issued_date     TEXT DEFAULT ({now_fn}),
            due_date        TEXT,
            subtotal        INTEGER,
            tax_amount      INTEGER DEFAULT 0,
            total_amount    INTEGER,
            status          TEXT DEFAULT 'unpaid',  -- unpaid|paid|overdue|cancelled
            paid_date       TEXT,
            notes           TEXT,
            created_at      TEXT DEFAULT ({now_fn})
        )""",

        # ── Revenue log (for dashboard) ────────────────────────────────────
        f"""CREATE TABLE IF NOT EXISTS revenue_log (
            id          {serial},
            invoice_id  INTEGER REFERENCES invoices(id),
            amount      INTEGER NOT NULL,
            currency    TEXT DEFAULT 'LKR',
            log_date    TEXT DEFAULT ({now_fn}),
            programme_id INTEGER REFERENCES programmes(id)
        )""",
    ]

    for stmt in statements:
        cur.execute(stmt)

    conn.commit()
    conn.close()
    _seed_data()


def _seed_data():
    """Insert default data if tables are empty."""
    from werkzeug.security import generate_password_hash

    # Seed admin user
    existing = query("SELECT id FROM users WHERE email = %s", ("admin@genbridge.lk",), fetchone=True)
    if not existing:
        query("""INSERT INTO users (email, password, name, role) VALUES (%s,%s,%s,%s)""",
              ("admin@genbridge.lk", generate_password_hash("Admin@2025", method="pbkdf2:sha256"), "Admin User", "admin"),
              commit=True)
        query("""INSERT INTO users (email, password, name, role) VALUES (%s,%s,%s,%s)""",
              ("trainer@genbridge.lk", generate_password_hash("Trainer@2025", method="pbkdf2:sha256"), "Priya Senanayake", "trainer"),
              commit=True)
        query("""INSERT INTO users (email, password, name, role) VALUES (%s,%s,%s,%s)""",
              ("hr@genbridge.lk", generate_password_hash("HR@2025", method="pbkdf2:sha256"), "Dilini Jayawardena", "hr_manager"),
              commit=True)

    # Seed trainer profile
    trainer_user = query("SELECT id FROM users WHERE role='trainer' LIMIT 1", fetchone=True)
    if trainer_user:
        existing_t = query("SELECT id FROM trainers WHERE user_id=%s", (trainer_user["id"],), fetchone=True)
        if not existing_t:
            specs = json.dumps(["Gen Z Integration", "Leadership Development", "Change Management"])
            query("""INSERT INTO trainers (user_id,bio,specialisations,qualifications,rating,sessions_count)
                     VALUES (%s,%s,%s,%s,%s,%s)""",
                  (trainer_user["id"],
                   "Senior facilitator with 12 years in corporate L&D across Sri Lanka and South Asia.",
                   specs, "MBA, CIPD Level 7, Certified DISC Practitioner", 4.9, 47),
                  commit=True)

    # Seed programmes
    if not query("SELECT id FROM programmes LIMIT 1", fetchone=True):
        progs = [
            ("GB-01","GenZ Workplace Launchpad","The essential one-day immersion for new Gen Z hires.","1 Day","In-Person",8500,12,20,"#0D7377"),
            ("GB-02","GenZ Professional Mastery","Two-day intensive for Gen Z professionals with 2+ years experience.","2 Days","Blended",16000,15,20,"#1B6B3A"),
            ("GB-03","Managing the Digital Native","One-day workshop for Gen X & Y managers.","1 Day","In-Person",12000,10,18,"#C0531A"),
            ("GB-04","Bridging the Generation Gap","1.5-day experiential for mixed workforce teams.","1.5 Days","In-Person",14000,16,24,"#5B2D8E"),
            ("GB-05","Executive GenZ Strategy","Half-day boardroom session for C-Suite & Directors.","Half Day","Workshop",25000,6,15,"#1B3A6B"),
            ("GB-06","Corporate Retainer Package","4 embedded sessions per month, 6-month contract.","Monthly","Blended",350000,1,1,"#C8962E"),
        ]
        for p in progs:
            query("""INSERT INTO programmes (code,name,description,duration,format,price_per_pax,min_pax,max_pax,accent_color)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", p, commit=True)

    # Seed sample workshops & bookings for dashboard demo data
    if not query("SELECT id FROM workshops LIMIT 1", fetchone=True):
        trainer = query("SELECT id FROM trainers LIMIT 1", fetchone=True)
        prog1   = query("SELECT id FROM programmes WHERE code='GB-01'", fetchone=True)
        prog3   = query("SELECT id FROM programmes WHERE code='GB-03'", fetchone=True)
        admin   = query("SELECT id FROM users WHERE role='admin'", fetchone=True)
        if trainer and prog1 and admin:
            tid, pid1, pid3, aid = trainer["id"], prog1["id"], prog3["id"], admin["id"]
            sample_workshops = [
                (pid1, tid, "GB-01 Cohort — Dialog Axiata", "2025-02-10 08:30", "2025-02-10 17:30", "Hilton Colombo", 20, "completed", aid),
                (pid3, tid, "GB-03 Manager Workshop — MAS Holdings", "2025-02-18 08:30", "2025-02-18 17:30", "Cinnamon Grand", 15, "completed", aid),
                (pid1, tid, "GB-01 Cohort — Hayleys PLC", "2025-03-05 08:30", "2025-03-05 17:30", "Kingsbury Hotel", 20, "completed", aid),
                (pid3, tid, "GB-03 Manager Workshop — Commercial Bank", "2025-03-20 08:30", "2025-03-20 17:30", "Client Premises", 12, "completed", aid),
                (pid1, tid, "GB-01 Cohort — Virtusa", "2025-04-08 08:30", "2025-04-08 17:30", "Trace Expert City", 18, "completed", aid),
                (pid3, tid, "GB-03 Workshop — Sampath Bank", "2025-04-22 08:30", "2025-04-22 17:30", "Sampath Centre", 14, "confirmed", aid),
                (pid1, tid, "GB-01 Cohort — IFS Sri Lanka", "2025-05-06 08:30", "2025-05-06 17:30", "IFS World Conference Centre", 20, "scheduled", aid),
                (pid3, tid, "GB-03 Manager Workshop — Brandix", "2025-05-19 08:30", "2025-05-19 17:30", "Brandix HQ Colombo", 16, "scheduled", aid),
            ]
            workshop_ids = []
            for w in sample_workshops:
                wid = query("""INSERT INTO workshops (programme_id,trainer_id,title,start_datetime,end_datetime,venue,max_capacity,status,created_by)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", w, commit=True)
                workshop_ids.append(wid)

            # Seed bookings + invoices for completed workshops
            sample_bookings = [
                (workshop_ids[0], "Ruwan Mendis",   "ruwan@dialog.lk",   "Dialog Axiata",    "+94771234567", 16, 16*8500),
                (workshop_ids[1], "Shehan De Silva","shehan@mas.com",     "MAS Holdings",     "+94772345678", 12, 12*12000),
                (workshop_ids[2], "Amali Fernando", "amali@hayleys.com",  "Hayleys PLC",      "+94773456789", 18, 18*8500),
                (workshop_ids[3], "Pradeep Wijeratne","pradeep@combank.lk","Commercial Bank",  "+94774567890", 10, 10*12000),
                (workshop_ids[4], "Kasun Perera",   "kasun@virtusa.com",  "Virtusa Lanka",    "+94775678901", 15, 15*8500),
            ]
            import random
            for i, b in enumerate(sample_bookings):
                booking_id = query("""INSERT INTO bookings (workshop_id,client_name,client_email,client_company,client_phone,pax_count,total_amount,status)
                                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                                   (*b, "confirmed"), commit=True)
                inv_num = f"INV-2025-{1000+i+1}"
                inv_id  = query("""INSERT INTO invoices (invoice_number,booking_id,subtotal,tax_amount,total_amount,status,paid_date,due_date)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                                (inv_num, booking_id, b[6], 0, b[6], "paid",
                                 f"2025-0{2+i//2}-{15+i*3}", f"2025-0{2+i//2}-{10+i*3}"),
                                commit=True)
                prog_id = pid1 if i % 2 == 0 else pid3
                query("INSERT INTO revenue_log (invoice_id,amount,programme_id) VALUES (%s,%s,%s)",
                      (inv_id, b[6], prog_id), commit=True)
