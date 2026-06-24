# Project Overview — AI Lead Generation & Outreach Platform

**Goal:** Automatically find local-business leads (schools, restaurants, hospitals, manufacturing, etc.), audit their websites with AI, score them, generate personalized outreach, send it over WhatsApp, and manage follow-ups in a CRM — so the user's agency can sell website dev, AI chatbots, WhatsApp automation, SEO, and AI agents.

## 3 Phases

**Phase 1 — MVP (~1–2 weeks, target early July 2026)**
Collect leads from Google Maps (Playwright + Crawl4AI) → store in PostgreSQL → website analyzer → AI audit agent → WhatsApp message generator.

Phase 1 steps:
1. **Google Maps leads** — City → search Schools/Restaurants/Hospitals → Business name, phone, website, address → PostgreSQL.
2. **Website Analyzer** — checks: website exists? SSL? mobile friendly? chatbot? WhatsApp button? booking form? Outputs JSON (e.g. `{"website": true, "chatbot": false, "whatsapp_button": false, "seo_score": 42}`).
3. **AI Audit Agent** — LLM analyzes site → Missing Features, AI Opportunities, Website Improvement, Lead Score. Output e.g. `{"lead_score": 92, "service": ["AI Chatbot","Website Redesign","WhatsApp Automation"]}`.
4. **Message Generator** — LLM writes a short, personalized WhatsApp outreach message per business.

**Phase 2 — Fully automated agent (LangGraph)**
Pipeline: Lead Agent → Audit Agent → Scoring Agent → Message Agent → CRM Agent.
Nodes: LeadCollectorNode, WebsiteAuditNode, OpportunityNode, MessageNode, CRMNode. Each node independent.

**Phase 3 — Agency scale**
- Multi-source lead finding: Google Maps, Google Search (`site:.in school/hospital/restaurant/manufacturing`), JustDial, IndiaMart, Sulekha, Yellow Pages.
- Vision-model screenshot audits (UI quality, SEO, trust signals, lead forms, AI opportunities).
- Supabase CRM (businesses, audits, messages, followups, meetings).
- WhatsApp Business API (or Playwright + WhatsApp Web at small scale).
- Dashboard + analytics.

## Timeline
Started **2026-06-24**; targeting a working system in **30–40 days** (late July / early Aug 2026).

## Status
- 2026-06-24: Planning captured in memory.
- 2026-06-24: **Phase 1 MVP scaffolded** in `backend/` — FastAPI app, PostgreSQL models (businesses/audits/messages/followups/meetings), Google Maps Playwright scraper, website analyzer, AI audit agent, rule-based scoring, message generator, pipeline orchestration, REST API. LLM via OpenRouter free model (primary) + GLM/Zhipu (fallback). See README.md.
- 2026-06-24: **Tested end-to-end & working.** Deps installed, Playwright chromium installed. DB switched to **SQLite** (`backend/leadgen.db`) for no-Docker local run. LLM = OpenRouter free model **`openai/gpt-oss-120b:free`** (deepseek free model got deprecated). AI pipeline verified: sample lead scored 75, audit + personalized WhatsApp message generated correctly.
- 2026-06-24: **WhatsApp sender built** (Playwright + WhatsApp Web, no API key, `.wa_session/` persistent). QR shown in dashboard via background login manager. Dry-run default ON (`WHATSAPP_DRY_RUN=true`).
- 2026-06-24: **Next.js dashboard built** (`frontend/`, Next 16 + React 19 + Tailwind v4). Single page: stats, 4-step progress, scrape form, QR connect, leads+messages list, Send All. Builds clean, serves HTTP 200. Talks to backend via `NEXT_PUBLIC_API_BASE`.
- Run: backend `cd backend && python run_dev.py` (port 8000); frontend `cd frontend && npm run dev` (port 3000).
- Next: Phase 2 (LangGraph nodes, Celery, follow-up agent Day 3/7/14/30); then real Postgres/Supabase, more lead sources.
