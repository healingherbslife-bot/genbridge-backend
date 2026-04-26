# GenBridge API Backend

Flask + SQLite/Neon PostgreSQL backend for the GenBridge Corporate Training platform.

---

## Features

| Feature | Details |
|---|---|
| **Authentication** | JWT-based login with role-based access (admin, trainer, hr_manager) |
| **Workshop Calendar** | Full CRUD scheduling with trainer assignment and capacity tracking |
| **Trainer Profiles** | Bio, specialisations, qualifications, rating, availability |
| **Bookings** | Client registration with automatic invoice generation |
| **Invoice Generator** | Pure-Python PDF invoices (no external PDF library needed) |
| **Revenue Dashboard** | Monthly trends, programme breakdown, KPI cards |
| **Admin SPA** | Full single-page admin dashboard at `/admin` |

---

## Quick Start (Local Development)

### 1. Clone / extract the project
```bash
cd genbridge-api
```

### 2. Create and activate a virtual environment
```bash
python3 -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment
```bash
cp .env.example .env
# Edit .env — at minimum change SECRET_KEY
```

### 5. Run the server
```bash
python app.py
```

The API starts on **http://localhost:5000**
The admin dashboard opens at **http://localhost:5000/admin**

---

## Default Login Credentials

| Role | Email | Password |
|---|---|---|
| Admin | admin@genbridge.lk | Admin@2025 |
| Trainer | trainer@genbridge.lk | Trainer@2025 |
| HR Manager | hr@genbridge.lk | HR@2025 |

> **Change all passwords immediately after first login in production.**

---

## Connecting to Neon (Production Database)

1. Go to [neon.tech](https://neon.tech) → Create a free project
2. Click **Connection Details** → Copy the connection string
3. Paste it into your `.env`:
   ```
   DATABASE_URL=postgresql://user:password@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
4. Install the PostgreSQL driver:
   ```bash
   pip install psycopg2-binary
   ```
5. Restart the server — it will auto-detect Neon and use it instead of SQLite

The schema is 100% PostgreSQL-compatible. The app auto-migrates on first boot.

---

## Deploying to Render (Recommended — Free Tier Available)

1. Push this folder to a GitHub repository
2. Go to [render.com](https://render.com) → **New → Web Service**
3. Connect your GitHub repo
4. Render auto-detects `render.yaml` — set the following env vars in the Render dashboard:
   - `SECRET_KEY` → click **Generate** in Render
   - `DATABASE_URL` → your Neon connection string
   - `ALLOWED_ORIGINS` → `https://your-netlify-site.netlify.app`
5. Deploy → your API will be live at `https://genbridge-api.onrender.com`

---

## Deploying to Railway

1. Go to [railway.app](https://railway.app) → **New Project → Deploy from GitHub**
2. Add environment variables from `.env.example`
3. Railway auto-detects the `Procfile`
4. Your API will be live at `https://genbridge-api.up.railway.app`

---

## Connecting the Frontend to the Backend

In your Netlify frontend site, set the API URL before the closing `</body>` tag on each page, or in a shared script:

```html
<script>
  window.API_URL = 'https://your-api.onrender.com';
</script>
```

For the admin dashboard specifically, the `API` constant in `public/admin/index.html` reads from `window.API_URL` automatically.

To update CORS, set `ALLOWED_ORIGINS` in your server env to include your Netlify domain:
```
ALLOWED_ORIGINS=https://genbridge.netlify.app,https://www.genbridge.lk
```

---

## API Reference

### Auth
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/login` | None | Login, returns JWT token |
| GET  | `/api/auth/me` | Required | Get current user |

### Workshops
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET  | `/api/workshops` | Required | List all (filter: `?month=YYYY-MM&status=`) |
| POST | `/api/workshops` | Admin/HR | Create workshop |
| GET  | `/api/workshops/:id` | Required | Get workshop + bookings |
| PUT  | `/api/workshops/:id` | Admin/HR | Update workshop |
| DELETE | `/api/workshops/:id` | Admin | Cancel workshop |
| GET  | `/api/workshops/calendar` | Required | Monthly calendar view |

### Trainers
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET  | `/api/trainers` | Required | List all trainer profiles |
| POST | `/api/trainers` | Admin | Create trainer profile |
| GET  | `/api/trainers/:id` | Required | Get trainer detail |
| PUT  | `/api/trainers/:id` | Admin/Trainer | Update profile |

### Bookings
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET  | `/api/bookings` | Required | List all bookings |
| POST | `/api/bookings` | Admin/HR | Create booking + auto-generate invoice |
| PUT  | `/api/bookings/:id` | Admin/HR | Update status |

### Invoices
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET  | `/api/invoices` | Required | List all invoices |
| GET  | `/api/invoices/:id` | Required | Invoice detail |
| GET  | `/api/invoices/:id/pdf` | Required | Download PDF invoice |
| PUT  | `/api/invoices/:id` | Admin/HR | Update (mark paid, etc.) |

### Dashboard & Revenue
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/dashboard` | Required | KPIs + upcoming + recent data |
| GET | `/api/revenue` | Admin/HR | Monthly/programme revenue analytics |

### Users
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET  | `/api/users` | Admin only | List all users |
| POST | `/api/users` | Admin only | Create user |
| PUT  | `/api/users/:id` | Admin only | Update / deactivate |

---

## Project Structure

```
genbridge-api/
├── app.py              # Main Flask application + all API routes
├── db.py               # Database layer (SQLite/Neon), schema, seed data
├── auth.py             # JWT auth + require_auth decorator
├── pdf_generator.py    # Pure-Python PDF invoice generator
├── requirements.txt    # Python dependencies
├── Procfile            # For Railway/Render deployment
├── render.yaml         # Render auto-deploy config
├── .env.example        # Environment variable template
└── public/
    └── admin/
        └── index.html  # Full admin dashboard SPA
```

---

## Security Notes

- All routes except `/api/auth/login` and `/api/health` require a valid JWT
- Role-based access: admin > hr_manager > trainer
- Passwords are hashed with Werkzeug's PBKDF2 (bcrypt-equivalent)
- CORS is restricted to `ALLOWED_ORIGINS` — never use `*` in production
- Rate limiting: implement via nginx or a service like Cloudflare in production
- **Always use HTTPS in production** — Neon requires SSL by default

---

## License

© 2025 GenBridge Corporate Training Solutions (Pvt) Ltd. All rights reserved.
