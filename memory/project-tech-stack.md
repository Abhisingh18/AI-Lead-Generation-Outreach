# Tech Stack

- **Backend:** FastAPI
- **Agent framework:** LangGraph
- **Scraping:** Playwright + Crawl4AI (+ BeautifulSoup for parsing)
- **Database:** PostgreSQL (see project-db-schema.md)
- **CRM / storage:** Supabase
- **Queue / async:** Redis + Celery (scheduling, retries, background jobs)
- **LLM:** GLM 5.2 primary, OpenRouter fallback — see project-llm-strategy.md
- **Embeddings:** BGE-M3
- **Vector DB:** Qdrant
- **Frontend:** Next.js + Tailwind + ShadCN
- **Vision (Phase 3 screenshot audits):** Qwen VL / GLM Vision / Kimi Vision
- **WhatsApp sending:** Meta WhatsApp Business API (preferred — legal/stable) OR Playwright + WhatsApp Web for small scale
- **Deployment:** Backend → Ubuntu VPS, Frontend → Vercel, Redis → Docker, Monitoring → Grafana

## Folder structure (proposed)
```
project/
  backend/
    agents/
    scrapers/
    database/
    api/
    tasks/
  frontend/
    dashboard/
    components/
    pages/
  docker/
  docs/
```
