# Deployment — Backend on Render, Frontend on Vercel

> **DB:** Render's own free PostgreSQL (no Supabase).
> **WhatsApp note:** WhatsApp sending needs a real browser + QR session, which a
> cloud box can't do easily. On Render it stays in dry-run. Run WhatsApp sending
> from your own laptop. Scraping + AI audit + **email** all work fine on Render.

---

## 0) Push the code to GitHub (needed for both Render & Vercel)

```bash
cd "f:/Automation for Leads Generation"
git init
git add .
git commit -m "AI lead gen platform"
# create an empty repo on github.com, then:
git remote add origin https://github.com/<you>/<repo>.git
git branch -M main
git push -u origin main
```

`.gitignore` already excludes `.env`, `.wa_session/`, `leadgen.db` — secrets won't be pushed.

---

## 1) Backend + Database on Render

1. Go to **render.com** → **New +** → **Blueprint**.
2. Connect your GitHub repo. Render reads **`render.yaml`** and creates:
   - `leadgen-backend` (Docker web service)
   - `leadgen-db` (free PostgreSQL, auto-wired into `DATABASE_URL`)
3. Before/after first deploy, set the **secret** env vars (marked `sync:false`) in the
   service's **Environment** tab:
   - `OPENROUTER_API_KEY` = your OpenRouter key
   - `EMAIL_APP_PASSWORD` = your Gmail app password
4. Deploy. First build takes a few minutes (installs Chromium).
5. Your backend URL will be like **`https://leadgen-backend.onrender.com`**.
   Test: open `https://leadgen-backend.onrender.com/health` → `{"status":"ok"}`.

Tables auto-create on startup. DB is Render Postgres (persistent).

> Free Render web services sleep after ~15 min idle and cold-start on next request
> (first hit is slow). Fine for now; upgrade later for always-on.

---

## 2) Frontend on Vercel

1. Go to **vercel.com** → **Add New** → **Project** → import the same repo.
2. **Root Directory:** set to **`frontend`**.
3. **Environment Variable:**
   - `NEXT_PUBLIC_API_BASE` = your Render backend URL
     (e.g. `https://leadgen-backend.onrender.com`)
4. Deploy. You get a URL like `https://your-app.vercel.app` — that's the dashboard.

(Backend CORS is open, so the Vercel frontend can call it. Tighten later if needed.)

---

## 3) WhatsApp sending (run locally)

WhatsApp stays dry-run on Render. To actually send WhatsApp:
- Run the backend on your **own laptop** (`cd backend && python run_dev.py`),
  point a local dashboard or the same hosted frontend at `http://localhost:8000`,
  connect WhatsApp (QR), and send.
- Email + scraping you can do entirely from the Render deployment.

---

## What runs where

| Component | Render | Vercel | Local laptop |
|-----------|:------:|:------:|:------------:|
| FastAPI API | ✅ | | |
| PostgreSQL | ✅ (free) | | |
| Google Maps scraping | ✅* | | ✅ |
| AI audit + email (Gmail) | ✅ | | ✅ |
| Dashboard (Next.js) | | ✅ | |
| WhatsApp sending | ⚠️ dry-run | | ✅ real |

\* Scraping from a datacenter IP may hit Google consent/captcha more often than your
home IP. If that happens, run scraping locally too.
