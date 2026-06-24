"""One-time WhatsApp Web login (RUN THIS IN YOUR OWN TERMINAL).

    python wa_login.py

A real Chromium window opens on YOUR screen -> scan the QR with your phone
(WhatsApp -> Linked Devices -> Link a Device). The login is saved in
WHATSAPP_SESSION_DIR, so afterwards the dashboard's "Send All" (which runs
headless) reuses it without asking for the QR again.

Make sure the backend is NOT sending at the same time (they share the browser
profile). Just have it idle, log in here, then use Send All.
"""

from app.senders.whatsapp_web import WhatsAppWebSender

if __name__ == "__main__":
    print("Opening WhatsApp Web… a window will appear. Scan the QR with your phone.")
    # Force a visible window regardless of the headless setting used for sending.
    with WhatsAppWebSender(headless=False) as wa:
        ok = wa.ensure_logged_in(qr_wait_seconds=180)
        print("\n✅ Logged in! You can close this and use Send All."
              if ok else "\n❌ Login failed / QR not scanned in time. Run again.")
