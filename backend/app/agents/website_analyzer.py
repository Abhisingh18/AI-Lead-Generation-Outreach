"""Website analyzer — fetches a site and detects technical signals.

No LLM here: pure HTTP + HTML heuristics. Produces the structured signals that
feed both the rule-based scorer and the AI audit agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup
from loguru import logger

# Pulls the phone number out of a WhatsApp link, e.g. wa.me/919876543210
WA_NUMBER_RE = re.compile(
    r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp\.com/send\?phone=|[?&]phone=)"
    r"\+?(\d[\d\-\s]{6,17}\d)",
    re.IGNORECASE,
)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
# Skip these — not real contact addresses.
_EMAIL_JUNK = (
    "example.com", "domain.com", "email.com", "yourdomain", "sentry.io",
    "wixpress.com", "@2x", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    "@sentry", "godaddy", "u003e", "u0040",
)


def _extract_email(html: str, soup: BeautifulSoup) -> str | None:
    """Find a business contact email (mailto links preferred), filtering junk."""
    candidates: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().startswith("mailto:"):
            addr = href[7:].split("?")[0].strip()
            if addr:
                candidates.append(addr)
    candidates += EMAIL_RE.findall(html)

    for raw in candidates:
        e = raw.strip().strip(".,;:").lower()
        if "@" not in e:
            continue
        if any(j in e for j in _EMAIL_JUNK):
            continue
        if len(e) > 80:
            continue
        return e
    return None

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Detection keyword sets (substring match against lowercased HTML)
CHATBOT_HINTS = [
    "intercom", "drift", "tawk.to", "tidio", "crisp.chat", "livechat",
    "freshchat", "zendesk", "chatbot", "botpress", "manychat", "wati",
]
WHATSAPP_HINTS = ["wa.me", "api.whatsapp.com", "whatsapp://", "click.to.chat", "web.whatsapp"]
BOOKING_HINTS = ["calendly", "booking", "appointment", "book now", "schedule", "reservation"]
FORM_HINTS = ["<form", "contact us", "get a quote", "enquir", "inquir"]
ANALYTICS_HINTS = ["googletagmanager", "google-analytics", "gtag(", "g-", "fbq("]


@dataclass
class WebsiteSignals:
    has_website: bool = False
    has_ssl: bool = False
    mobile_friendly: bool = False
    has_chatbot: bool = False
    has_whatsapp: bool = False
    has_lead_form: bool = False
    has_booking: bool = False
    has_analytics: bool = False
    seo_score: int | None = None
    whatsapp_number: str | None = None  # digits-only, extracted from wa.me links
    email: str | None = None            # contact email scraped from the site
    page_excerpt: str = ""
    extra: dict = field(default_factory=dict)


def _seo_score(soup: BeautifulSoup, html: str) -> int:
    """Rough 0-100 on-page SEO heuristic."""
    score = 0
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    if 10 <= len(title) <= 70:
        score += 25
    elif title:
        score += 10

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and (meta_desc.get("content") or "").strip():
        score += 20

    if soup.find("h1"):
        score += 15

    imgs = soup.find_all("img")
    if imgs:
        with_alt = sum(1 for i in imgs if (i.get("alt") or "").strip())
        score += int(15 * with_alt / len(imgs))

    if soup.find("meta", attrs={"property": "og:title"}):
        score += 10
    if soup.find("link", attrs={"rel": "canonical"}):
        score += 5
    if soup.find("meta", attrs={"name": "viewport"}):
        score += 10
    return min(score, 100)


def _contains_any(haystack: str, needles: list[str]) -> bool:
    return any(n in haystack for n in needles)


def analyze_website(url: str | None) -> WebsiteSignals:
    """Fetch `url` and return technical signals. Safe to call with None/invalid URL."""
    signals = WebsiteSignals()
    if not url:
        return signals

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=20.0,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = client.get(url)
            final_url = str(resp.url)
            html = resp.text or ""
    except Exception as exc:
        logger.warning("Could not fetch {}: {}", url, exc)
        return signals

    signals.has_website = True
    signals.has_ssl = final_url.startswith("https://")

    lowered = html.lower()
    soup = BeautifulSoup(html, "lxml")

    signals.mobile_friendly = soup.find("meta", attrs={"name": "viewport"}) is not None
    signals.has_chatbot = _contains_any(lowered, CHATBOT_HINTS)
    signals.has_whatsapp = _contains_any(lowered, WHATSAPP_HINTS)
    if signals.has_whatsapp:
        m = WA_NUMBER_RE.search(html)
        if m:
            digits = re.sub(r"\D", "", m.group(1))
            if 8 <= len(digits) <= 15:
                signals.whatsapp_number = digits
    signals.has_booking = _contains_any(lowered, BOOKING_HINTS)
    signals.has_lead_form = _contains_any(lowered, FORM_HINTS)
    signals.has_analytics = _contains_any(lowered, ANALYTICS_HINTS)
    signals.seo_score = _seo_score(soup, html)
    signals.email = _extract_email(html, soup)

    # Visible text excerpt for the AI audit agent
    text = " ".join(soup.get_text(separator=" ").split())
    signals.page_excerpt = text[:1500]

    logger.debug(
        "Analyzed {}: ssl={} chatbot={} wa={} seo={}",
        url, signals.has_ssl, signals.has_chatbot, signals.has_whatsapp, signals.seo_score,
    )
    return signals
