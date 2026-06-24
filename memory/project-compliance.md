# Compliance & Safety (IMPORTANT)

Large-scale automated scraping/messaging of Google Maps, WhatsApp, and websites must respect platform policies, anti-spam rules, and applicable privacy laws.

Production version MUST implement:
- **Public business contacts only** (no private/personal data harvesting).
- **Consent-based outreach.**
- **Rate limiting** on scraping and messaging.
- **Opt-out handling** for recipients.

The system is technically powerful, but the compliance layer is equally important. WhatsApp Business API is the legal/stable channel; WhatsApp Web automation via Playwright carries higher policy risk and is only for small scale.
