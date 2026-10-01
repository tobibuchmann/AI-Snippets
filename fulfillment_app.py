import base64
import html
import io
import json
import os
import threading
import time
from datetime import datetime, timezone, timedelta

import requests
from flask import Flask, jsonify, request
from openai import OpenAI
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import create_engine, text

try:
    import stripe
except Exception:
    stripe = None

app = Flask(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None


def now_utc():
    return datetime.now(timezone.utc)


def now_iso():
    return now_utc().isoformat()


def get_order(order_id):
    if not engine:
        return None
    with engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM orders WHERE id=:id"), {"id": order_id}).mappings().first()
        return dict(row) if row else None


def update_order(order_id, status, generated_text=None, session_id=None):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE orders
            SET status=:status,
                generated_text=COALESCE(:generated_text, generated_text),
                stripe_session_id=COALESCE(:session_id, stripe_session_id),
                updated_at=:updated_at
            WHERE id=:id
        """), {
            "status": status,
            "generated_text": generated_text,
            "session_id": session_id,
            "updated_at": now_iso(),
            "id": order_id,
        })


def claim_generation(order_id, session_id=None):
    stale_before = (now_utc() - timedelta(minutes=2)).isoformat()
    with engine.begin() as conn:
        row = conn.execute(text("""
            UPDATE orders
            SET status='generating',
                stripe_session_id=COALESCE(:session_id, stripe_session_id),
                updated_at=:updated_at
            WHERE id=:id
              AND generated_text IS NULL
              AND status <> 'delivered'
              AND (status <> 'generating' OR updated_at < :stale_before)
            RETURNING id
        """), {
            "session_id": session_id,
            "updated_at": now_iso(),
            "stale_before": stale_before,
            "id": order_id,
        }).first()
        return row is not None


def build_prompt(payload):
    locations = payload.get("locations") or []
    return f"""Du bist Autor und Spieldesigner für hochwertige, sichere Kindergeburtstage.
Erstelle ein vollständig spielbares, personalisiertes Geburtstags-Abenteuer mit genau 8 Stationen und etwa 45–60 Minuten Spielzeit.

Daten:
Geburtstagskind: {payload.get('child_name', '')}
Alter: {payload.get('age', '')}
Gruppengröße: {payload.get('group_size', '')}
Interessen: {payload.get('interests', '')}
Thema: {payload.get('theme', '')}
Spielbereich: {payload.get('play_area', '')}
Nutzbare Orte: {', '.join(locations)}
Weitere Orte: {payload.get('other_locations', '')}
Tabu-Orte: {payload.get('forbidden_locations', '')}
Finale: {payload.get('final_location', '')}
Hinweise: {payload.get('notes', '')}

Vorgaben:
- Geburtstagskind zentral und positiv einbinden.
- Genau 8 Stationen; jede führt eindeutig zur nächsten.
- Mix aus Logik, Beobachtung, Bewegung, Kooperation, Codes sowie Wort-/Zahlenrätseln.
- Nur erlaubte Orte verwenden.
- Kein Feuer, keine Elektrizität, keine Straße, kein gefährliches Klettern, keine scharfen Gegenstände, keine verschlossenen Räume.
- Keine bekannten Franchise-Figuren oder geschützten Welten.
- Keine Lebensmittel als zwingende Mechanik.
- Lösungen eindeutig und altersgerecht.
- Formuliere druckfertig und verständlich für Eltern.

Ausgabe in sauberem Markdown:
1. Titel
2. Kurzbeschreibung für Eltern
3. Materialliste
4. Vorbereitungstabelle
5. Einstiegsgeschichte (max. 300 Wörter)
6. Station 1–8 jeweils mit Geschichte, Kinderkarte, Aufgabe, Elternlösung, nächstem Ort, Tipp
7. Finale
8. Persönliche Urkunde
9. 10-Minuten-Zusatzspiel
10. Endprüfung der Route und Lösungen.
"""


def generate_quest(payload):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=180.0)
    model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
    response = client.responses.create(
        model=model,
        input=build_prompt(payload),
        reasoning={"effort": "low"},
    )
    return response.output_text


def markdown_to_pdf_bytes(title, content):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
        author="GeburtstagsQuest",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("QuestTitle", parent=styles["Title"], alignment=TA_CENTER, spaceAfter=10)
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], spaceBefore=10, spaceAfter=6)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["BodyText"], leading=15, spaceAfter=5)

    story = [Paragraph(html.escape(title), title_style), Spacer(1, 6)]
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 5))
        elif line.startswith("# "):
            story.append(Paragraph(html.escape(line[2:]), h1))
        elif line.startswith("## "):
            story.append(Paragraph(html.escape(line[3:]), h2))
        elif line.startswith("### "):
            story.append(Paragraph(f"<b>{html.escape(line[4:])}</b>", body))
        elif line.startswith("---"):
            story.append(PageBreak())
        elif line.startswith("- "):
            story.append(Paragraph("• " + html.escape(line[2:]), body))
        else:
            story.append(Paragraph(html.escape(line), body))

    doc.build(story)
    return buffer.getvalue()


def send_email(to_email, pdf_bytes, order_id):
    payload = {
        "from": os.environ["RESEND_FROM_EMAIL"],
        "to": [to_email],
        "subject": "Deine GeburtstagsQuest ist fertig",
        "html": (
            "<p>Hallo,</p>"
            "<p>deine personalisierte GeburtstagsQuest ist fertig.</p>"
            "<p>Im Anhang findest du die druckfertige PDF mit Geschichte, 8 Stationen, Lösungen, Finale und Urkunde.</p>"
            "<p>Viel Spaß bei eurem Abenteuer!</p>"
            "<p>GeburtstagsQuest</p>"
        ),
        "attachments": [{
            "filename": f"GeburtstagsQuest-{order_id}.pdf",
            "content": base64.b64encode(pdf_bytes).decode("ascii"),
            "content_type": "application/pdf",
        }],
    }
    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
            "Content-Type": "application/json",
            "Idempotency-Key": f"geburtstagsquest-delivery-{order_id}",
        },
        json=payload,
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(f"Resend HTTP {response.status_code}: {response.text[:500]}")
    return response.json()


def fulfill(order_id, session_id=None):
    order = get_order(order_id)
    if not order:
        raise ValueError("order_not_found")
    if order["status"] == "delivered":
        return {"status": "already_delivered"}

    payload = json.loads(order["payload"])
    generated = order.get("generated_text")

    if not generated:
        if not claim_generation(order_id, session_id=session_id):
            latest = get_order(order_id)
            if latest and latest.get("generated_text"):
                generated = latest["generated_text"]
            else:
                return {"status": "generation_in_progress"}
        else:
            try:
                generated = generate_quest(payload)
                update_order(order_id, "generated", generated_text=generated, session_id=session_id)
            except Exception:
                update_order(order_id, "fulfillment_failed", session_id=session_id)
                raise

    try:
        pdf_bytes = markdown_to_pdf_bytes(f"GeburtstagsQuest für {payload.get('child_name', '')}", generated)
        email_result = send_email(order["email"], pdf_bytes, order_id)
        update_order(order_id, "delivered", generated_text=generated, session_id=session_id)
        return {"status": "delivered", "email_id": email_result.get("id")}
    except Exception:
        update_order(order_id, "delivery_failed", generated_text=generated, session_id=session_id)
        raise


def run_fulfillment(order_id, session_id=None):
    try:
        result = fulfill(order_id, session_id)
        app.logger.warning("Fulfillment result order=%s status=%s", order_id, result.get("status"))
    except Exception:
        app.logger.exception("Fulfillment failed for %s", order_id)


def queue_fulfillment(order_id, session_id=None):
    thread = threading.Thread(target=run_fulfillment, args=(order_id, session_id), daemon=True)
    thread.start()


def stripe_webhook_secrets():
    return [value for value in [
        os.getenv("FULFILLMENT_STRIPE_WEBHOOK_SECRET", ""),
        os.getenv("FULFILLMENT_STRIPE_WEBHOOK_SECRET_TEST", ""),
    ] if value]


def verify_stripe_event(raw, signature):
    last_error = None
    for secret in stripe_webhook_secrets():
        try:
            return stripe.Webhook.construct_event(raw, signature, secret)
        except Exception as exc:
            last_error = exc
    raise last_error or ValueError("no_webhook_secret")


def recover_stale_jobs():
    time.sleep(8)
    if not engine:
        return
    try:
        stale_before = (now_utc() - timedelta(minutes=2)).isoformat()
        with engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT id, stripe_session_id
                FROM orders
                WHERE (
                    status = 'delivery_failed' AND generated_text IS NOT NULL
                ) OR (
                    generated_text IS NULL
                    AND status IN ('generating', 'fulfillment_failed')
                    AND updated_at < :stale_before
                )
                ORDER BY updated_at ASC
                LIMIT 20
            """), {"stale_before": stale_before}).mappings().all()
        app.logger.warning("Recovery scan found %s pending fulfillment job(s)", len(rows))
        for row in rows:
            app.logger.warning("Recovering fulfillment order=%s", row["id"])
            queue_fulfillment(row["id"], row.get("stripe_session_id"))
    except Exception:
        app.logger.exception("Stale fulfillment recovery failed")


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "database_configured": bool(DATABASE_URL),
        "stripe_live_webhook_configured": bool(os.getenv("FULFILLMENT_STRIPE_WEBHOOK_SECRET")),
        "stripe_test_webhook_configured": bool(os.getenv("FULFILLMENT_STRIPE_WEBHOOK_SECRET_TEST")),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "resend_configured": bool(os.getenv("RESEND_API_KEY") and os.getenv("RESEND_FROM_EMAIL")),
    })


@app.post("/stripe-webhook")
def stripe_webhook():
    if stripe is None or not stripe_webhook_secrets():
        return jsonify({"error": "webhook_not_configured"}), 503

    raw = request.get_data(cache=False, as_text=False)
    signature = request.headers.get("Stripe-Signature", "")
    try:
        event = verify_stripe_event(raw, signature)
    except Exception:
        return jsonify({"error": "invalid_signature"}), 400

    event_type = event.get("type")
    if event_type not in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        return jsonify({"received": True, "ignored": event_type})

    session = event.get("data", {}).get("object", {})
    if session.get("payment_status") != "paid":
        return jsonify({"received": True, "payment_status": session.get("payment_status")})

    order_id = (session.get("metadata") or {}).get("order_id") or session.get("client_reference_id")
    if not order_id:
        return jsonify({"error": "order_id_missing"}), 400

    queue_fulfillment(order_id, session.get("id"))
    return jsonify({"received": True, "queued": True})


threading.Thread(target=recover_stale_jobs, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
