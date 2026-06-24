# LLM & Cost Strategy

**Primary LLM:** GLM 5.2 (Zhipu AI) — free/cheap, long context, good reasoning. Enough for website audit, opportunity detection, and message generation.

**Fallback / scale:** OpenRouter models — DeepSeek V3, Qwen3, Kimi, GLM, Gemini. Add paid models when processing 500–1000 leads/day.

**Vision (UI/screenshot audits):** Qwen VL / GLM Vision / Kimi Vision. GLM vision quality may not be top-tier.

## Where LLM is / isn't needed
- **Needs LLM:** Website Audit Agent, Opportunity Agent, Message Generator. (Lead scoring can use LLM OR a rule engine — rule engine is more reliable.)
- **No LLM needed:** Lead collection (Playwright/Crawl4AI/BeautifulSoup), CRM memory (PostgreSQL/Supabase), WhatsApp sending.

## Lead scoring (rule engine preferred)
```
No Website      = +30
No WhatsApp     = +20
No Chatbot      = +20
Poor SEO        = +15
Low Review Count= +10
No Online Booking = +15
```
Bands: 0–40 Low, 40–70 Medium, 70–100 High.

## Budget tiers
- **₹0–₹500/month:** GLM 5.2 + Playwright + Crawl4AI + PostgreSQL + FastAPI + LangGraph.
- **₹1000–₹3000/month:** Add OpenRouter (Qwen3, DeepSeek), GLM 5.2 as backup.
- **₹5000+/month:** Premium OpenRouter models, better vision models, WhatsApp Business API, dedicated VPS.
