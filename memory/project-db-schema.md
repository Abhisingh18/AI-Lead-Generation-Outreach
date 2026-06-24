# Database Schema (PostgreSQL)

All collected data must be permanently saved.

## businesses
id, name, category, website, phone, email, address, city, state, rating, reviews, status, created_at, updated_at

## website_audits
id, business_id, has_website, has_ssl, mobile_friendly, has_chatbot, has_whatsapp, seo_score, ai_opportunity_score, audit_summary, created_at

## messages
id, business_id, message, status, sent_at, created_at

## followups
id, business_id, followup_number, message, status, created_at

## meetings
id, business_id, meeting_date, notes, status, created_at

---
**Data collected per lead:** Business Name, Category, Owner Name (if public), Website, Phone, Email, Address, Google Rating, Review Count, City, State.
