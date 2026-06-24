"""Google Maps lead scraper using Playwright.

Scrapes public business listings (name, phone, website, address, rating, reviews)
for a given city + category. Includes randomized delays and scroll-based pagination.

COMPLIANCE: only collect public business contact data, respect rate limits, and
honor platform policies + local privacy law. Keep volumes modest and add opt-out
handling before any outreach. See memory/project-compliance.md.
"""

from __future__ import annotations

import asyncio
import random
import re
from dataclasses import dataclass, field

from loguru import logger
from playwright.async_api import Page, async_playwright

from app.config import settings

MAPS_SEARCH_URL = "https://www.google.com/maps/search/{query}"


@dataclass
class ScrapedBusiness:
    name: str
    category: str | None = None
    phone: str | None = None
    website: str | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None
    dial_code: str | None = None
    rating: float | None = None
    reviews: int | None = None
    source: str = "google_maps"
    extra: dict = field(default_factory=dict)


async def _human_delay() -> None:
    await asyncio.sleep(random.uniform(settings.scraper_delay_min, settings.scraper_delay_max))


def _parse_rating_reviews(text: str) -> tuple[float | None, int | None]:
    """Parse aria-labels like '4.3 stars 128 Reviews'."""
    rating = None
    reviews = None
    if not text:
        return rating, reviews
    rmatch = re.search(r"([0-9]\.[0-9])", text)
    if rmatch:
        rating = float(rmatch.group(1))
    vmatch = re.search(r"([\d,]+)\s*(?:review|Review)", text)
    if vmatch:
        reviews = int(vmatch.group(1).replace(",", ""))
    return rating, reviews


async def _scroll_results(page: Page, target: int) -> None:
    """Scroll the results feed until we have enough cards or hit the end."""
    feed = page.locator('div[role="feed"]')
    last_count = 0
    stagnant = 0
    while stagnant < 4:
        cards = await page.locator('div[role="feed"] a[href*="/maps/place/"]').count()
        if cards >= target:
            break
        await feed.evaluate("el => el.scrollBy(0, el.scrollHeight)")
        await asyncio.sleep(random.uniform(1.2, 2.4))
        if cards == last_count:
            stagnant += 1
        else:
            stagnant = 0
        last_count = cards


async def _extract_detail(page: Page) -> ScrapedBusiness | None:
    """Extract fields from an opened business detail panel."""
    try:
        name = await page.locator("h1").first.inner_text(timeout=5000)
    except Exception:
        return None

    biz = ScrapedBusiness(name=name.strip())

    # Address
    try:
        addr = page.locator('button[data-item-id="address"]')
        if await addr.count():
            biz.address = (await addr.first.get_attribute("aria-label") or "").replace(
                "Address: ", ""
            ).strip()
    except Exception:
        pass

    # Phone
    try:
        phone = page.locator('button[data-item-id^="phone:tel:"]')
        if await phone.count():
            biz.phone = (await phone.first.get_attribute("aria-label") or "").replace(
                "Phone: ", ""
            ).strip()
    except Exception:
        pass

    # Website
    try:
        site = page.locator('a[data-item-id="authority"]')
        if await site.count():
            biz.website = await site.first.get_attribute("href")
    except Exception:
        pass

    # Rating / reviews
    try:
        rr = page.locator('div[role="img"][aria-label*="stars"]')
        if await rr.count():
            label = await rr.first.get_attribute("aria-label") or ""
            biz.rating, biz.reviews = _parse_rating_reviews(label)
    except Exception:
        pass

    return biz


async def scrape_google_maps(
    city: str,
    category: str,
    max_results: int | None = None,
    country: str | None = None,
    dial_code: str | None = None,
) -> list[ScrapedBusiness]:
    """Scrape up to `max_results` businesses for `category` in `city` (any country)."""
    limit = max_results or settings.scraper_max_results
    location = f"{city}, {country}" if country else city
    query = f"{category} in {location}".replace(" ", "+")
    url = MAPS_SEARCH_URL.format(query=query)
    results: list[ScrapedBusiness] = []
    seen: set[str] = set()

    logger.info("Scraping Google Maps: '{}' in '{}' (limit={})", category, city, limit)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.scraper_headless)
        context = await browser.new_context(
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await _human_delay()

        # Consent screen handling (best effort)
        try:
            consent = page.get_by_role("button", name=re.compile("Accept all|Reject all"))
            if await consent.count():
                await consent.first.click()
                await _human_delay()
        except Exception:
            pass

        try:
            await page.wait_for_selector('div[role="feed"]', timeout=15000)
        except Exception:
            logger.warning("No results feed appeared for query '{}'", query)
            await browser.close()
            return results

        await _scroll_results(page, limit)

        links = page.locator('div[role="feed"] a[href*="/maps/place/"]')
        count = min(await links.count(), limit)
        hrefs = [await links.nth(i).get_attribute("href") for i in range(count)]

        for href in hrefs:
            if not href or href in seen:
                continue
            seen.add(href)
            try:
                await page.goto(href, wait_until="domcontentloaded", timeout=45000)
                await _human_delay()
                biz = await _extract_detail(page)
                if biz and biz.name:
                    biz.category = category
                    biz.city = city
                    biz.country = country
                    biz.dial_code = dial_code
                    results.append(biz)
                    logger.debug("Scraped: {} | {}", biz.name, biz.phone)
            except Exception as exc:
                logger.warning("Failed to extract a listing: {}", exc)
            if len(results) >= limit:
                break

        await browser.close()

    logger.info("Scraped {} businesses for '{}' in '{}'", len(results), category, city)
    return results
