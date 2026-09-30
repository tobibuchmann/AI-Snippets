import base64
import html
import io
import json
import os
from datetime import datetime, timezone

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


def now_iso():
    return datetime.now(timezone.utc).isoformat()


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


def build_prompt(payload):
    return f"""Du bist Autor und Spieldesigner für hochwertige, sichere Kindergeburtstage.
Erstelle ein vollständig spielbares, personalisiertes Geburtstags-Abenteuer mit genau 8 Stationen und etwa 45–60 Minuten Spielzeit.

Daten:
Geburtstagskind: {payload['child_name']}
Alter: {payload['age']}
Gruppengröße: {payload['group_size']}
Interessen: {payload['interests']}
Thema: {payload['theme']}
Spielbereich: {payload['play_area']}
Nutzbare Orte: {', '.join(payload['locations'])}
Weitere Orte: {payload['other_locations']}
Tabu-Orte: {payload['forbidden_locations']}
Finale: {payload['final_location']}
Hinweise: {payload['notes']}

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
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    response = client.responses.create(model=model, input=build_prompt(payload))
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
    title_style = ParagraphStyle(
        "QuestTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], spaceBefore=10, spaceAfter=6)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["BodyText"], leading=15, spaceAfter=5)

    story = [Paragraph(html.escape(title), title_style), Spacer(1, 6)]
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 5))
            continue
        safe = html.escape(line)
        if line.startswith("# "):
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
            story.append(Paragraph(safe, body))

    doc.build(story)
    return buffer.getvalue()


def send_email(to_email, child_name, pdf_bytes, order_id):
    api_key = os.environ["RESEND_API_KEY"]
    from_email = os.environ["RESEND_FROM_EMAIL"]
    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": f"Deine GeburtstagsQuest für {child_name}",
        "html": (
            f"<p>Hallo,</p>"
            f"<p>deine personalisierte GeburtstagsQuest für <strong>{html.escape(child_name)}</strong> ist fertig.</p>"
            f"<p>Im Anhang findest du die druckfertige PDF mit Geschichte, 8 Stationen, Lösungen, Finale und Urkunde.</p>"
            f"<p>Viel Spaß bei eurem Abenteuer!</p>"
            f"<p>GeburtstagsQuest</p>"
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
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": f"geburtstagsquest-delivery-{order_id}",
        },
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
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
        generated = generate_quest(payload)
        update_order(order_id, "generated", generated_text=generated, session_id=session_id)

    pdf_bytes = markdown_to_pdf_bytes(f"GeburtstagsQuest für {payload['child_name']}", generated)
    email_result = send_email(order["email"], payload["child_name"], pdf_bytes, order_id)
    update_order(order_id, "delivered", generated_text=generated, session_id=session_id)
    return {"status": "delivered", "email_id": email_result.get("id")}


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "database_configured": bool(DATABASE_URL),
        "stripe_webhook_configured": bool(os.getenv("FULFILLMENT_STRIPE_WEBHOOK_SECRET")),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "resend_configured": bool(os.getenv("RESEND_API_KEY") and os.getenv("RESEND_FROM_EMAIL")),
    })


@app.post("/stripe-webhook")
def stripe_webhook():
    secret = os.getenv("FULFILLMENT_STRIPE_WEBHOOK_SECRET", "")
    if stripe is None or not secret:
        return jsonify({"error": "webhook_not_configured"}), 503

    raw = request.get_data(cache=False, as_text=False)
    signature = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(raw, signature, secret)
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

    try:
        result = fulfill(order_id, session.get("id"))
        return jsonify({"received": True, **result})
    except Exception as exc:
        app.logger.exception("Fulfillment failed for %s", order_id)
        return jsonify({"error": "fulfillment_failed", "detail": str(exc)[:200]}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
