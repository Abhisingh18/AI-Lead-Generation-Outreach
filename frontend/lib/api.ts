// Thin client for the FastAPI backend.

// Uses NEXT_PUBLIC_API_BASE if set, else the deployed Render backend.
// Local dev overrides this via frontend/.env.local (http://localhost:8000).
const BASE =
  process.env.NEXT_PUBLIC_API_BASE || "https://leadgen-backend-l31l.onrender.com";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} ${text}`);
  }
  return res.json() as Promise<T>;
}

export type Stats = {
  total_leads: number;
  qualified_leads: number;
  whatsapp_ready: number;
  email_ready: number;
  messages_sent: number;
  messages_draft: number;
};

export type Lead = {
  id: number;
  name: string;
  category: string | null;
  city: string | null;
  country: string | null;
  phone: string | null;
  whatsapp_number: string | null;
  email: string | null;
  website: string | null;
  rating: number | null;
  reviews: number | null;
  lead_score: number | null;
  status: string | null;
  audit_summary: string | null;
  message_id: number | null;
  message: string | null;
  message_status: string | null;
  channel: string | null;
  subject: string | null;
};

export type WaStatus = {
  status: string;
  logged_in: boolean;
  qr: string | null;
  error: string | null;
};

export type ScrapeStatus = {
  running: boolean;
  phase: string; // idle | scraping | processing | done | error
  total: number;
  done: number;
  city: string;
  category: string;
  country: string;
  error: string | null;
};

export type SendStatus = {
  running: boolean;
  phase: string; // idle | sending | done | error
  total: number;
  done: number;
  sent: number;
  error: string | null;
  results: Array<{
    business?: string;
    phone?: string;
    ok: boolean;
    dry_run?: boolean;
    error: string | null;
  }>;
};

export const api = {
  stats: () => req<Stats>("/api/stats"),
  leads: () => req<Lead[]>("/api/dashboard/leads?limit=200"),
  scrape: (
    city: string,
    category: string,
    max_results: number,
    country: string,
    dial_code: string
  ) =>
    req("/api/scrape", {
      method: "POST",
      body: JSON.stringify({
        city,
        category,
        country,
        dial_code,
        max_results,
        run_pipeline: true,
      }),
    }) as Promise<{ started: boolean } & ScrapeStatus>,
  scrapeStatus: () => req<ScrapeStatus>("/api/scrape/status"),
  waConnect: () => req<WaStatus>("/api/whatsapp/connect", { method: "POST" }),
  waStatus: () => req<WaStatus>("/api/whatsapp/status"),
  sendBatch: (min_score: number, limit: number) =>
    req<{ started: boolean; error?: string } & SendStatus>(
      `/api/send/batch?min_score=${min_score}&limit=${limit}`,
      { method: "POST" }
    ),
  sendStatus: () => req<SendStatus>("/api/send/status"),
  sendEmails: (min_score: number, limit: number) =>
    req<{ started: boolean; error?: string } & SendStatus>(
      `/api/send/emails?min_score=${min_score}&limit=${limit}`,
      { method: "POST" }
    ),
  sendEmailsStatus: () => req<SendStatus>("/api/send/emails/status"),
  sendOne: (messageId: number) =>
    req(`/api/messages/${messageId}/send`, { method: "POST" }),
};
