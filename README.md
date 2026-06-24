# AI Lead Generation & Outreach Platform

Find local-business leads from Google Maps, audit their web presence with AI,
score them with a rule engine, and auto-generate personalized WhatsApp outreach —
all stored in PostgreSQL.

> **Phase 1 (MVP) is implemented in `backend/`.** Phase 2 (LangGraph automation)
> and Phase 3 (multi-source + vision audits + dashboard) are planned — see
> [`memory/`](memory/) for the full roadmap.

## Pipeline

```
Google Maps  ->  Lead Collector  ->  PostgreSQL
                                          |
                  Website Analyzer (HTTP/HTML signals)
                                          |
                  AI Audit Agent (LLM: opportunities + services)
                                          |
                  Lead Scoring (rule engine, 0-100)
                                          |
                  Message Generator (LLM: WhatsApp draft)
```

## Tech

FastAPI · SQLAlchemy · PostgreSQL · Playwright · BeautifulSoup · httpx ·
OpenRouter / GLM (Zhipu) via OpenAI-compatible API.

---

## Setup

### 1. Start Postgres (Docker)

```bash
docker compose up -d db
```

(Or use your own Postgres / Supabase and update `DATABASE_URL`.)

### 2. Python env + dependencies

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows (PowerShell: .venv\Scripts\Activate.ps1)
pip install -r requirements.txt
python -m playwright install chromium
```

### 3. Configure secrets

`backend/.env` already exists (gitignored). Confirm `LLM_PROVIDER`, keys, and
`DATABASE_URL`. Copy from `.env.example` if you need a fresh one.

### 4. Run the API

```bash
python run_dev.py
# -> http://localhost:8000/docs  (interactive Swagger UI)
```

Tables are auto-created on startup.

---

## Usage

### Scrape + run full pipeline

```bash
curl -X POST http://localhost:8000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{"city":"Jaipur","category":"restaurants","max_results":10,"run_pipeline":true}'
```

### Browse leads (best opportunities first)

```bash
curl "http://localhost:8000/api/leads?min_score=70&limit=20"
```

### Other endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/scrape` | Scrape Google Maps, persist, optionally run pipeline |
| GET  | `/api/leads` | List/filter leads (`city`, `category`, `status`, `min_score`) |
| GET  | `/api/leads/{id}` | Single lead |
| POST | `/api/leads/{id}/process` | Re-run audit/score/message for a lead |
| GET  | `/api/leads/{id}/audits` | Audit history |
| GET  | `/api/leads/{id}/messages` | Generated messages |
| GET  | `/api/stats` | Dashboard counters |
| POST | `/api/messages/{id}/send` | Send one drafted WhatsApp message |
| POST | `/api/send/batch` | Send all drafts (best leads first, daily cap) |

### Send on WhatsApp

1. **Login once** (scan QR with your number `9648531091`):
   ```bash
   cd backend
   python wa_login.py
   ```
2. **Test safely** with `WHATSAPP_DRY_RUN=true` (default) — simulates sends, marks DB.
3. When ready, set `WHATSAPP_DRY_RUN=false` in `.env`, then:
   ```bash
   curl -X POST "http://localhost:8000/api/send/batch?min_score=70&limit=10"
   ```

---

## LLM models

Set in `.env`. Default is an OpenRouter **free** model. Strong free options:

- `deepseek/deepseek-chat-v3.1:free`
- `meta-llama/llama-3.3-70b-instruct:free`
- `qwen/qwen-2.5-72b-instruct:free`

GLM (Zhipu) is configured as a fallback — set `LLM_PROVIDER=zhipu` to use it.
Free models on OpenRouter have rate limits; if you hit them, switch provider/model.

---

## ⚠️ Security & Compliance

- **Never commit `.env`.** It is gitignored. If a key was ever pasted in chat or
  shared, **rotate it** in the provider dashboard.
- Collect **public business contact data only**. Respect Google Maps / WhatsApp
  platform policies, rate limits, and applicable privacy law. Add **consent-based
  outreach** and **opt-out handling** before sending at scale. See
  [`memory/project-compliance.md`](memory/project-compliance.md).

## Roadmap

- **Phase 2:** Port the pipeline to independent LangGraph nodes; Celery scheduling; follow-up agent (Day 3/7/14/30).
- **Phase 3:** JustDial/IndiaMart/Sulekha sources, Playwright screenshot + vision-model UI audits, WhatsApp Business API sender, Next.js dashboard + analytics.
