# Agents & Workflow

## End-to-end pipeline
```
Google Maps
   ↓
Lead Collector
   ↓
PostgreSQL
   ↓
Website Audit Agent (GLM 5.2)
   ↓
Opportunity Agent
   ↓
Lead Scoring Agent
   ↓
Message Generator (GLM 5.2)
   ↓
WhatsApp Seender
   ↓
Follow-up Agent
   ↓
CRM Dashboard
```

## Agents

**AI Audit Agent** — checks: website exists, SSL, responsive design, chatbot, WhatsApp integration, lead form, online booking, SEO meta tags, Google Analytics, page speed, trust signals.
Output: `{"lead_score": 92, "problems": [], "opportunities": [], "recommended_services": []}`

**AI Opportunity Agent** — identifies services to sell: Website Development, Website Redesign, AI Chatbot, WhatsApp Automation, CRM Automation, SEO Service, Lead Generation, Voice Agent, Customer Support Agent, Appointment Booking Agent, Lead Scoring Agent.

**Personalized Outreach Agent** — generates business-specific WhatsApp message, Email message, Follow-up message, Proposal message.

**WhatsApp Automation** — Meta WhatsApp Business API (preferred) or Playwright + WhatsApp Web. Features: send message, track status, retry failed, schedule messages.

**Follow-up Agent** — automatic follow-ups on Day 3, 7, 14, 30 if no response.

## Advanced / future
- Screenshot analysis: Playwright screenshot → vision model → UI audit.
- Voice calling agent: Vapi / Retell AI / Bland AI.
- Meeting booking: Google Calendar / Calendly.

## Dashboard (Next.js)
Pages: Dashboard, Leads, Audits, Messages, Followups, Meetings, Settings, Analytics.
Analytics: Total Leads, Qualified Leads, Messages Sent, Replies Received, Meetings Booked, Conversion Rate, Revenue Generated.
