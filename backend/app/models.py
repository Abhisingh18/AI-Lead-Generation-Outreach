"""ORM models — businesses, website_audits, messages, followups, meetings."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LeadStatus(str, enum.Enum):
    NEW = "new"
    AUDITED = "audited"
    SCORED = "scored"
    MESSAGE_READY = "message_ready"
    CONTACTED = "contacted"
    REPLIED = "replied"
    MEETING = "meeting"
    WON = "won"
    LOST = "lost"


class MessageChannel(str, enum.Enum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"


class MessageStatus(str, enum.Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    REPLIED = "replied"


class Business(Base):
    __tablename__ = "businesses"
    __table_args__ = (
        # Avoid duplicate leads for the same name+city.
        UniqueConstraint("name", "city", name="uq_business_name_city"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str | None] = mapped_column(String(120), index=True)
    owner_name: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(512))
    phone: Mapped[str | None] = mapped_column(String(64), index=True)
    whatsapp_number: Mapped[str | None] = mapped_column(String(32), index=True)  # WA-ready (digits)
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    state: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120), index=True)
    dial_code: Mapped[str | None] = mapped_column(String(8))  # e.g. "91", "1", "44"
    rating: Mapped[float | None] = mapped_column(Float)
    reviews: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(String(64), default="google_maps")
    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus), default=LeadStatus.NEW, index=True
    )
    lead_score: Mapped[int | None] = mapped_column(Integer, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    audits: Mapped[list[WebsiteAudit]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    messages: Mapped[list[Message]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    followups: Mapped[list[Followup]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    meetings: Mapped[list[Meeting]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )


class WebsiteAudit(Base):
    __tablename__ = "website_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )

    # Technical signals (from website analyzer)
    has_website: Mapped[bool] = mapped_column(Boolean, default=False)
    has_ssl: Mapped[bool] = mapped_column(Boolean, default=False)
    mobile_friendly: Mapped[bool] = mapped_column(Boolean, default=False)
    has_chatbot: Mapped[bool] = mapped_column(Boolean, default=False)
    has_whatsapp: Mapped[bool] = mapped_column(Boolean, default=False)
    has_lead_form: Mapped[bool] = mapped_column(Boolean, default=False)
    has_booking: Mapped[bool] = mapped_column(Boolean, default=False)
    has_analytics: Mapped[bool] = mapped_column(Boolean, default=False)
    seo_score: Mapped[int | None] = mapped_column(Integer)

    # AI signals (from audit agent)
    ai_opportunity_score: Mapped[int | None] = mapped_column(Integer)
    problems: Mapped[str | None] = mapped_column(Text)              # JSON string
    opportunities: Mapped[str | None] = mapped_column(Text)         # JSON string
    recommended_services: Mapped[str | None] = mapped_column(Text)  # JSON string
    audit_summary: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    business: Mapped[Business] = relationship(back_populates="audits")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[MessageChannel] = mapped_column(
        Enum(MessageChannel), default=MessageChannel.WHATSAPP
    )
    subject: Mapped[str | None] = mapped_column(String(255))  # used for email
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus), default=MessageStatus.DRAFT, index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    business: Mapped[Business] = relationship(back_populates="messages")


class Followup(Base):
    __tablename__ = "followups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    followup_number: Mapped[int] = mapped_column(Integer, default=1)  # 1,2,3,4 -> day 3/7/14/30
    body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus), default=MessageStatus.DRAFT
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    business: Mapped[Business] = relationship(back_populates="followups")


class Contacted(Base):
    """Lightweight log of leads we've already reached out to.

    When a WhatsApp/email is sent, the heavy lead data (business, audits, message
    bodies) is deleted to keep the DB lean, and a tiny row is kept here so we never
    re-scrape or re-contact the same business.
    """

    __tablename__ = "contacted"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), index=True)
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    phone: Mapped[str | None] = mapped_column(String(64))
    whatsapp_number: Mapped[str | None] = mapped_column(String(32), index=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    channel: Mapped[str | None] = mapped_column(String(20))   # whatsapp | email
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    meeting_date: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="scheduled")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    business: Mapped[Business] = relationship(back_populates="meetings")
