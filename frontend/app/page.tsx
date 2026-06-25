"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Lead, type ScrapeStatus, type Stats, type WaStatus } from "@/lib/api";
import { COUNTRIES, flagOf } from "@/lib/countries";

const STEPS = ["Find Leads", "AI Audit & Message", "Connect WhatsApp", "Send"];

function scoreColor(s: number | null) {
  if (s == null) return "bg-slate-400";
  if (s >= 70) return "bg-emerald-500";
  if (s >= 40) return "bg-amber-500";
  return "bg-slate-400";
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [wa, setWa] = useState<WaStatus | null>(null);

  const [city, setCity] = useState("Jaipur");
  const [category, setCategory] = useState("restaurants");
  const [countryIdx, setCountryIdx] = useState(0);
  const [maxResults, setMaxResults] = useState(10);

  const [scraping, setScraping] = useState(false);
  const [progress, setProgress] = useState<ScrapeStatus | null>(null);
  const [sending, setSending] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [autoSend, setAutoSend] = useState(true);
  const [log, setLog] = useState<string[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const note = (m: string) =>
    setLog((l) => [`${new Date().toLocaleTimeString()}  ${m}`, ...l].slice(0, 8));

  const refresh = useCallback(async () => {
    try {
      const [s, l] = await Promise.all([api.stats(), api.leads()]);
      setStats(s);
      setLeads(l);
    } catch (e) {
      note("Backend offline? " + (e as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  // Auto-connect WhatsApp on load (QR appears by itself — no button tap needed).
  const autoConnectedRef = useRef(false);
  useEffect(() => {
    if (autoSend && !autoConnectedRef.current) {
      autoConnectedRef.current = true;
      onConnect();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSend]);

  const hasLeads = leads.length > 0;
  const hasMessages = leads.some((l) => l.message);
  const waReadyCount = leads.filter((l) => l.whatsapp_number && l.message).length;
  const emailReadyCount = leads.filter(
    (l) => !l.whatsapp_number && l.email && l.message
  ).length;
  const connected = wa?.logged_in ?? false;
  const sent = (stats?.messages_sent ?? 0) > 0;
  const currentStep = connected || sent ? 3 : hasMessages ? 2 : hasLeads ? 1 : 0;

  async function onScrape() {
    const c = COUNTRIES[countryIdx];
    setScraping(true);
    setProgress(null);
    note(`Scraping "${category}" in ${city}, ${c.name}…`);
    try {
      const res = await api.scrape(city, category, maxResults, c.name, c.dial);
      if (!res.started) {
        note("A scrape is already running.");
      }
      // Poll progress; leads appear live via the 5s refresh.
      const poll = setInterval(async () => {
        try {
          const st = await api.scrapeStatus();
          setProgress(st);
          await refresh();
          if (!st.running) {
            clearInterval(poll);
            setScraping(false);
            note(
              st.phase === "error"
                ? "Scrape error: " + st.error
                : `Done — ${st.done}/${st.total} leads analyzed.`
            );
            // Auto-send: fire WhatsApp + Email without any button tap.
            if (autoSend && st.phase !== "error") {
              note("Auto-send: sending WhatsApp + emails…");
              onSendAll(true);
              onSendEmails(true);
            }
          }
        } catch {
          /* ignore transient poll errors */
        }
      }, 2500);
    } catch (e) {
      note("Scrape failed: " + (e as Error).message);
      setScraping(false);
    }
  }

  async function onConnect() {
    try {
      const s = await api.waConnect();
      setWa(s);
      if (s.status === "disabled") {
        note("WhatsApp disabled on this server — email works here.");
        return; // don't poll; cloud server can't run WhatsApp
      }
      note("Opening WhatsApp session… scan the QR with your phone.");
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const st = await api.waStatus();
          setWa(st);
          if (st.logged_in || st.status === "error" || st.status === "disabled") {
            if (pollRef.current) clearInterval(pollRef.current);
            note(st.logged_in ? "WhatsApp connected ✓" : "QR error: " + st.error);
          }
        } catch {
          /* ignore poll errors */
        }
      }, 2500);
    } catch (e) {
      note("Connect failed: " + (e as Error).message);
    }
  }

  async function onSendEmails(silent = false) {
    if (!silent && !confirm("Send emails to leads that have NO WhatsApp number?")) return;
    setSendingEmail(true);
    note("Starting emails…");
    try {
      const r = await api.sendEmails(0, 50);
      if (!r.started) {
        note("Cannot email: " + (r.error || "an email send is already running"));
        setSendingEmail(false);
        return;
      }
      const poll = setInterval(async () => {
        try {
          const st = await api.sendEmailsStatus();
          await refresh();
          if (!st.running) {
            clearInterval(poll);
            setSendingEmail(false);
            note(
              st.phase === "error"
                ? "Email error: " + st.error
                : `Emails done. Sent ${st.sent} of ${st.total}.`
            );
          } else {
            note(`Emailing ${st.done}/${st.total}…`);
          }
        } catch {
          /* ignore */
        }
      }, 2000);
    } catch (e) {
      note("Email failed: " + (e as Error).message);
      setSendingEmail(false);
    }
  }

  async function onSendAll(silent = false) {
    if (!silent && !confirm("Send WhatsApp messages to all listed leads?")) return;
    setSending(true);
    note("Starting send…");
    try {
      const r = await api.sendBatch(0, 50);
      if (!r.started) {
        note("Cannot send: " + (r.error || "a send is already running"));
        setSending(false);
        return;
      }
      const poll = setInterval(async () => {
        try {
          const st = await api.sendStatus();
          await refresh();
          if (!st.running) {
            clearInterval(poll);
            setSending(false);
            note(
              st.phase === "error"
                ? "Send error: " + st.error
                : `Done. Delivered ${st.sent} of ${st.total} (rest: number not on WhatsApp).`
            );
          } else {
            note(`Processing ${st.done}/${st.total} · delivered ${st.sent}…`);
          }
        } catch {
          /* ignore transient poll errors */
        }
      }, 2000);
    } catch (e) {
      note("Send failed: " + (e as Error).message);
      setSending(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-4 sm:px-5 py-6 sm:py-8">
      <header className="mb-7 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-indigo-600 text-white text-xl font-bold shadow-lg shadow-indigo-600/30">
            ⚡
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-800">
              AI Lead Generation &amp; Outreach
            </h1>
            <p className="text-slate-500 text-sm">
              Find local businesses → audit with AI → personalized WhatsApp outreach.
            </p>
          </div>
        </div>
        <button
          onClick={() => setAutoSend((v) => !v)}
          className={`shrink-0 rounded-full px-4 py-2 text-sm font-semibold border transition ${
            autoSend
              ? "bg-emerald-600 text-white border-emerald-600 shadow-md shadow-emerald-600/30"
              : "bg-white text-slate-500 border-slate-300"
          }`}
          title="When ON: after scraping, WhatsApp + emails send automatically (no button tap)."
        >
          {autoSend ? "⚡ Full Auto: ON" : "Full Auto: OFF"}
        </button>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-6">
        <Stat label="Total Leads" value={stats?.total_leads} accent="text-slate-800" />
        <Stat label="Qualified (70+)" value={stats?.qualified_leads} accent="text-emerald-600" />
        <Stat label="WhatsApp-ready" value={stats?.whatsapp_ready} accent="text-green-600" />
        <Stat label="Email-ready" value={stats?.email_ready} accent="text-sky-600" />
        <Stat label="Drafts" value={stats?.messages_draft} accent="text-indigo-600" />
        <Stat label="Sent" value={stats?.messages_sent} accent="text-green-700" />
      </section>

      <section className="flex items-center gap-2 mb-7 overflow-x-auto pb-1">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center gap-2 shrink-0">
            <div
              className={`flex items-center gap-2 rounded-full px-3.5 py-1.5 text-sm border transition ${
                i <= currentStep
                  ? "bg-indigo-50 border-indigo-300 text-indigo-700 font-medium"
                  : "bg-white border-slate-200 text-slate-400"
              }`}
            >
              <span
                className={`grid h-5 w-5 place-items-center rounded-full text-xs font-bold ${
                  i <= currentStep ? "bg-indigo-600 text-white" : "bg-slate-200 text-slate-500"
                }`}
              >
                {i + 1}
              </span>
              {s}
            </div>
            {i < STEPS.length - 1 && <span className="text-slate-300">→</span>}
          </div>
        ))}
      </section>

      <div className="grid md:grid-cols-3 gap-5">
        <div className="space-y-5">
          <Card title="1 · Find Leads">
            <label className="block text-xs text-slate-500 mb-1">Country / Market</label>
            <select
              className="input"
              value={countryIdx}
              onChange={(e) => setCountryIdx(Number(e.target.value))}
            >
              {COUNTRIES.map((c, i) => (
                <option key={`${c.iso2}-${i}`} value={i}>
                  {flagOf(c.iso2)} {c.name} (+{c.dial})
                </option>
              ))}
            </select>
            <label className="block text-xs text-slate-500 mt-3 mb-1">City</label>
            <input className="input" value={city} onChange={(e) => setCity(e.target.value)} />
            <label className="block text-xs text-slate-500 mt-3 mb-1">Category</label>
            <input
              className="input"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />
            <label className="block text-xs text-slate-500 mt-3 mb-1">
              Max results: <span className="font-semibold text-slate-700">{maxResults}</span>
            </label>
            <input
              type="range"
              min={1}
              max={100}
              value={maxResults}
              onChange={(e) => setMaxResults(Number(e.target.value))}
              className="w-full accent-indigo-600"
            />
            <button className="btn-primary mt-4 w-full" disabled={scraping} onClick={onScrape}>
              {scraping
                ? progress?.phase === "scraping"
                  ? "Scraping Google Maps…"
                  : progress && progress.total > 0
                    ? `Analyzing ${progress.done}/${progress.total}…`
                    : "Starting…"
                : "Find & Analyze Leads"}
            </button>
            {scraping && progress && progress.total > 0 && (
              <div className="mt-2 h-1.5 w-full rounded bg-slate-200 overflow-hidden">
                <div
                  className="h-full bg-indigo-600 transition-all"
                  style={{ width: `${(progress.done / progress.total) * 100}%` }}
                />
              </div>
            )}
          </Card>

          <Card title="3 · Connect WhatsApp">
            {wa?.status === "disabled" ? (
              <div className="text-sm">
                <div className="text-amber-600 font-medium">WhatsApp not available here</div>
                <p className="text-xs text-slate-500 mt-1">
                  This cloud server has no screen, so WhatsApp can&apos;t run. Email works
                  here. To send WhatsApp, run the backend on your laptop.
                </p>
              </div>
            ) : connected ? (
              <div className="flex items-center gap-2 text-emerald-600 text-sm font-semibold">
                <span className="grid h-5 w-5 place-items-center rounded-full bg-emerald-100">
                  ✓
                </span>
                Connected
              </div>
            ) : wa?.link_code ? (
              <div className="text-center">
                <p className="text-xs text-slate-500 mb-2">
                  On your phone: WhatsApp → <b>Linked Devices</b> → <b>Link a Device</b> →
                  <b> Link with phone number instead</b> → type this code:
                </p>
                <div className="text-2xl font-bold tracking-[0.3em] text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-lg py-3">
                  {wa.link_code}
                </div>
                <p className="text-[11px] text-slate-400 mt-2">
                  Works on the same phone — no QR scanning needed.
                </p>
              </div>
            ) : wa?.qr ? (
              <div className="text-center">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={wa.qr}
                  alt="WhatsApp QR"
                  className="mx-auto rounded-lg border border-slate-200 bg-white p-2 w-48 h-48 object-contain"
                />
                <p className="text-xs text-slate-500 mt-2">
                  WhatsApp → Linked Devices → Link a Device → scan this.
                </p>
              </div>
            ) : wa?.status === "waiting_qr" || wa?.status === "starting" ? (
              <div className="text-sm">
                <div className="flex items-center gap-2 text-indigo-600 font-medium">
                  <span className="h-3 w-3 rounded-full bg-indigo-500 animate-pulse" />
                  {wa.status === "starting" ? "Opening WhatsApp…" : "Window opened — scan now"}
                </div>
                <p className="text-xs text-slate-500 mt-2">
                  A WhatsApp Web window opened on your screen. On your phone: WhatsApp →
                  Linked Devices → Link a Device → scan the QR in that window. Waiting…
                </p>
              </div>
            ) : (
              <>
                {wa?.status === "error" && (
                  <p className="text-xs text-rose-600 mb-2">
                    {wa.error || "Login failed"} — try again.
                  </p>
                )}
                <p className="text-xs text-slate-500 mb-3">
                  Scan once with your number. A browser window will open. Session stays saved.
                </p>
                <button className="btn w-full" onClick={onConnect}>
                  Connect WhatsApp
                </button>
              </>
            )}
          </Card>

          <Card title="4 · Send">
            <p className="text-xs text-slate-500 mb-3">
              <span className="text-green-600 font-medium">WhatsApp</span> for leads with a
              number, <span className="text-sky-600 font-medium">Email</span> for the rest.
              (Dry-run unless disabled in .env.)
            </p>
            <button
              className="btn-green w-full mb-2"
              disabled={sending || waReadyCount === 0}
              onClick={() => onSendAll()}
            >
              {sending ? "Sending…" : `Send WhatsApp (${waReadyCount})`}
            </button>
            <button
              className="btn-primary w-full"
              disabled={sendingEmail || emailReadyCount === 0}
              onClick={() => onSendEmails()}
            >
              {sendingEmail ? "Emailing…" : `Send Emails (${emailReadyCount})`}
            </button>
          </Card>

          <Card title="Activity">
            <ul className="text-xs text-slate-500 space-y-1">
              {log.length === 0 && <li>No activity yet.</li>}
              {log.map((l, i) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
          </Card>
        </div>

        <div className="md:col-span-2">
          <Card title={`2 · Leads & Messages (${leads.length})`}>
            {leads.length === 0 ? (
              <p className="text-slate-500 text-sm">
                No leads yet. Use “Find &amp; Analyze Leads”.
              </p>
            ) : (
              <div className="space-y-3 max-h-[72vh] overflow-y-auto pr-1">
                {leads.map((l) => (
                  <div
                    key={l.id}
                    className="rounded-xl border border-slate-200 bg-white p-3.5 hover:shadow-md transition"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="font-semibold text-slate-800">{l.name}</div>
                        <div className="text-xs text-slate-500">
                          {[l.category, l.city, l.country, l.phone]
                            .filter(Boolean)
                            .join(" · ")}
                        </div>
                        {l.whatsapp_number ? (
                          <div className="mt-1 inline-flex items-center gap-1 rounded bg-green-100 text-green-700 text-[11px] font-medium px-1.5 py-0.5">
                            ✓ WhatsApp: +{l.whatsapp_number}
                          </div>
                        ) : l.email ? (
                          <div className="mt-1 inline-flex items-center gap-1 rounded bg-sky-100 text-sky-700 text-[11px] font-medium px-1.5 py-0.5">
                            ✉ Email: {l.email}
                          </div>
                        ) : (
                          <div className="mt-1 inline-flex items-center gap-1 rounded bg-slate-100 text-slate-400 text-[11px] px-1.5 py-0.5">
                            no WhatsApp / email
                          </div>
                        )}
                      </div>
                      <span
                        className={`text-white text-xs font-bold rounded-lg px-2.5 py-1 ${scoreColor(
                          l.lead_score
                        )}`}
                      >
                        {l.lead_score ?? "–"}
                      </span>
                    </div>
                    {l.audit_summary && (
                      <p className="text-xs text-slate-500 mt-2 italic">{l.audit_summary}</p>
                    )}
                    {l.message && (
                      <div className="mt-2 rounded-lg bg-slate-50 border border-slate-200 p-2.5 text-sm text-slate-700">
                        <div className="mb-1 text-[10px] uppercase tracking-wide font-semibold text-slate-400">
                          {l.channel === "email" ? "✉ Email" : "WhatsApp"}
                        </div>
                        {l.channel === "email" && l.subject && (
                          <div className="font-semibold text-slate-800 mb-1">
                            {l.subject}
                          </div>
                        )}
                        <div className="whitespace-pre-wrap">{l.message}</div>
                      </div>
                    )}
                    <div className="mt-1.5 flex items-center gap-2 text-[11px]">
                      <span
                        className={`rounded px-1.5 py-0.5 font-medium ${
                          l.message_status === "sent"
                            ? "bg-green-100 text-green-700"
                            : l.message_status === "draft"
                              ? "bg-indigo-100 text-indigo-700"
                              : "bg-slate-100 text-slate-500"
                        }`}
                      >
                        {l.message_status ?? "no message"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>

      <footer className="mt-8 text-center text-xs text-slate-400">
        Built for outreach to public business contacts · respect rate limits &amp; opt-outs.
      </footer>
    </main>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value?: number;
  accent: string;
}) {
  return (
    <div className="card p-4">
      <div className={`text-2xl font-bold ${accent}`}>{value ?? "–"}</div>
      <div className="text-xs text-slate-500 mt-0.5">{label}</div>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-4">
      <h2 className="text-sm font-semibold text-slate-500 mb-3 uppercase tracking-wide text-[11px]">
        {title}
      </h2>
      {children}
    </div>
  );
}
