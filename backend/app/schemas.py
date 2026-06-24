"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import LeadStatus, MessageChannel, MessageStatus

# ---------------- Businesses ----------------


class BusinessBase(BaseModel):
    name: str
    category: str | None = None
    owner_name: str | None = None
    website: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    dial_code: str | None = None
    rating: float | None = None
    reviews: int | None = None
    source: str | None = "google_maps"


class BusinessCreate(BusinessBase):
    pass


class BusinessOut(BusinessBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: LeadStatus
    lead_score: int | None = None
    created_at: datetime
    updated_at: datetime


# ---------------- Scrape request ----------------


class ScrapeRequest(BaseModel):
    city: str
    category: str            # e.g. "restaurants", "schools", "hospitals"
    country: str | None = None    # e.g. "USA", "Germany" — sharpens the Maps query
    dial_code: str = "91"         # WhatsApp country dialing code (no +). 1=US, 44=UK, 91=India
    max_results: int | None = None
    run_pipeline: bool = True  # auto-run audit + score + message after scraping


# ---------------- Audit ----------------


class WebsiteAuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    has_website: bool
    has_ssl: bool
    mobile_friendly: bool
    has_chatbot: bool
    has_whatsapp: bool
    has_lead_form: bool
    has_booking: bool
    has_analytics: bool
    seo_score: int | None
    ai_opportunity_score: int | None
    problems: str | None
    opportunities: str | None
    recommended_services: str | None
    audit_summary: str | None
    created_at: datetime


# ---------------- Messages ----------------


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    channel: MessageChannel
    body: str
    status: MessageStatus
    sent_at: datetime | None
    created_at: datetime


# ---------------- Pipeline result ----------------


class PipelineResult(BaseModel):
    business_id: int
    name: str
    lead_score: int | None
    audit_id: int | None
    message_id: int | None
    error: str | None = None
