import json
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import create_engine, text

try:
    import stripe
except Exception:
    stripe = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

app = Flask(__name__)
SITE_URL = os.getenv("SITE_URL", "https://geburtstagsquest.onrender.com").rstrip("/")
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", SITE_URL)
PAYMENTS_MODE = os.getenv("PAYMENTS_MODE", "test").strip().lower()
if PAYMENTS_MODE not in {"test", "live"}:
    PAYMENTS_MODE = "test"
STRIPE_TEST_PAYMENT_LINK = os.getenv("STRIPE_TEST_PAYMENT_LINK", "").strip()
STRIPE_LIVE_PAYMENT_LINK = os.getenv("STRIPE_LIVE_PAYMENT_LINK", "").strip()
CORS(app, resources={r"/api/*": {"origins": [ALLOWED_ORIGIN, SITE_URL]}})

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////tmp/geburtstagsquest-orders.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS orders (
                id VARCHAR(64) PRIMARY KEY,
                email VARCHAR(320) NOT NULL,
                child_name VARCHAR(80) NOT NULL,
                payload TEXT NOT NULL,
                status VARCHAR(40) NOT NULL,
                stripe_session_id VARCHAR(255),
                generated_text TEXT,
                created_at VARCHAR(64) NOT NULL,
                updated_at VARCHAR(64) NOT NULL
            )
        """))


init_db()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_order(order_id):
    with engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM orders WHERE id=:id"), {"id": order_id}).mappings().first()
        return dict(row) if row else None


def get_order_by_session(session_id):
    if not session_id:
        return None
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT * FROM orders WHERE stripe_session_id=:session_id ORDER BY updated_at DESC LIMIT 1"),
            {"session_id": session_id},
        ).mappings().first()
        return dict(row) if row else None


def set_status(order_id, status, stripe_session_id=None):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE orders
            SET status=:status,
                stripe_session_id=COALESCE(:stripe_session_id, stripe_session_id),
                updated_at=:updated_at
            WHERE id=:id
        """), {
            "status": status,
            "stripe_session_id": stripe_session_id,
            "updated_at": now_iso(),
            "id": order_id,
        })


def selected_payment_link():
    if PAYMENTS_MODE == "live":
        return STRIPE_LIVE_PAYMENT_LINK
    return STRIPE_TEST_PAYMENT_LINK


def stripe_secret_mode():
    secret = os.getenv("STRIPE_SECRET_KEY", "")
    if secret.startswith("sk_live_"):
        return "live"
    if secret.startswith("sk_test_"):
        return "test"
    return "unknown" if secret else "none"


def accepted(value):
    return str(value or "").strip().lower() in {"yes", "on", "true", "1"}


def allowed(value, choices, fallback):
    value = str(value or "").strip()
    return value if value in choices else fallback


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "payments_mode": PAYMENTS_MODE,
        "stripe_secret_configured": bool(os.getenv("STRIPE_SECRET_KEY")),
        "stripe_secret_mode": stripe_secret_mode(),
        "stripe_payment_link_configured": bool(selected_payment_link()),
        "stripe_webhook_configured": bool(os.getenv("STRIPE_WEBHOOK_SECRET")),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "database": "postgres" if "postgresql" in DATABASE_URL else "temporary_sqlite",
        "adaptive_order_fields": True,
        "session_lookup": True,
    })


@app.post("/api/orders")
def create_order():
    data = request.get_json(silent=True) or {}
    required = [
        "child_name", "age", "group_size", "theme", "play_area", "email",
        "reading_level", "math_level", "difficulty", "activity_level", "desired_duration",
    ]
    missing = [k for k in required if not str(data.get(k, "")).strip()]
    if missing:
        return jsonify({"error": "missing_fields", "fields": missing}), 400

    privacy_acknowledged = accepted(data.get("privacy_notice_acknowledged")) or accepted(data.get("consent"))
    if not privacy_acknowledged:
        return jsonify({"error": "privacy_notice_acknowledgement_required"}), 400
    if not accepted(data.get("digital_content_consent")):
        return jsonify({"error": "digital_content_consent_required"}), 400

    locations = data.get("locations") or []
    if not isinstance(locations, list) or not locations:
        return jsonify({"error": "locations_required"}), 400

    reading_level = allowed(data.get("reading_level"), {"vorlesen", "kurze_saetze", "sicher"}, "kurze_saetze")
    math_level = allowed(data.get("math_level"), {"ohne", "bis20", "bis100", "altersgerecht"}, "altersgerecht")
    difficulty = allowed(data.get("difficulty"), {"leicht", "ausgewogen", "knifflig"}, "ausgewogen")
    activity_level = allowed(data.get("activity_level"), {"ruhig", "ausgewogen", "viel"}, "ausgewogen")
    desired_duration = allowed(data.get("desired_duration"), {"30", "45", "60"}, "45")

    order_id = "gq_" + uuid.uuid4().hex[:20]
    created = now_iso()
    payload = {
        "child_name": str(data.get("child_name", ""))[:80],
        "age": str(data.get("age", ""))[:10],
        "group_size": str(data.get("group_size", ""))[:10],
        "interests": str(data.get("interests", ""))[:1000],
        "reading_level": reading_level,
        "math_level": math_level,
        "difficulty": difficulty,
        "activity_level": activity_level,
        "desired_duration": desired_duration,
        "theme": str(data.get("theme", ""))[:120],
        "play_area": str(data.get("play_area", ""))[:120],
        "locations": [str(x)[:120] for x in locations[:20]],
        "other_locations": str(data.get("other_locations", ""))[:1000],
        "forbidden_locations": str(data.get("forbidden_locations", ""))[:1000],
        "final_location": str(data.get("final_location", ""))[:300],
        "notes": str(data.get("notes", ""))[:2000],
        "privacy_notice_acknowledged": True,
        "privacy_notice_acknowledged_at": created,
        "privacy_notice_version": "2026-10-06-v2",
        "digital_content_consent": True,
        "digital_content_consent_at": created,
        "digital_content_consent_version": "2026-10-06-v2",
    }

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO orders (id, email, child_name, payload, status, created_at, updated_at)
            VALUES (:id, :email, :child_name, :payload, 'created', :created_at, :updated_at)
        """), {
            "id": order_id,
            "email": str(data.get("email", ""))[:320],
            "child_name": payload["child_name"],
            "payload": json.dumps(payload, ensure_ascii=False),
            "created_at": created,
            "updated_at": created,
        })

    return jsonify({"order_id": order_id, "status": "created"})


@app.post("/api/create-checkout")
def create_checkout():
    data = request.get_json(silent=True) or {}
    order_id = str(data.get("order_id", ""))
    order = get_order(order_id)
    if not order:
        return jsonify({"error": "order_not_found"}), 404

    secret = os.getenv("STRIPE_SECRET_KEY", "")
    if stripe is not None and secret and stripe_secret_mode() == PAYMENTS_MODE:
        stripe.api_key = secret
        session = stripe.checkout.Session.create(
            mode="payment",
            customer_email=order["email"],
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "unit_amount": 3900,
                    "product_data": {
                        "name": "GeburtstagsQuest",
                        "description": "Personalisiertes Kindergeburtstags-Abenteuer mit 8 Stationen als PDF",
                    },
                },
                "quantity": 1,
            }],
            metadata={"order_id": order_id},
            client_reference_id=order_id,
            success_url=f"{SITE_URL}/zahlung-erfolgreich.html?session_id={{CHECKOUT_SESSION_ID}}&order_id={order_id}",
            cancel_url=f"{SITE_URL}/bestellen.html?zahlung=abgebrochen",
            locale="de",
        )
        set_status(order_id, "checkout_created", session.id)
        return jsonify({"checkout_url": session.url, "mode": "checkout_session", "payments_mode": PAYMENTS_MODE})

    payment_link = selected_payment_link()
    if payment_link:
        query = urlencode({
            "client_reference_id": order_id,
            "prefilled_email": order["email"],
        })
        separator = "&" if "?" in payment_link else "?"
        checkout_url = payment_link + separator + query
        set_status(order_id, "checkout_created")
        return jsonify({"checkout_url": checkout_url, "mode": "payment_link", "payments_mode": PAYMENTS_MODE})

    return jsonify({"error": "payments_not_configured"}), 503


@app.post("/api/stripe-webhook")
def stripe_webhook():
    if stripe is None or not os.getenv("STRIPE_WEBHOOK_SECRET"):
        return jsonify({"error": "webhook_not_configured"}), 503

    payload = request.get_data(cache=False, as_text=False)
    signature = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload,
            signature,
            os.environ["STRIPE_WEBHOOK_SECRET"],
        )
    except Exception:
        return jsonify({"error": "invalid_signature"}), 400

    if event.get("type") == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = (session.get("metadata") or {}).get("order_id") or session.get("client_reference_id")
        if order_id and session.get("payment_status") == "paid":
            set_status(order_id, "paid", session.get("id"))

    return jsonify({"received": True})


def verify_paid(order_id, session_id):
    secret = os.getenv("STRIPE_SECRET_KEY", "")
    if stripe is None or not secret or stripe_secret_mode() != PAYMENTS_MODE:
        return False, "payment_verification_not_configured"
    stripe.api_key = secret
    session = stripe.checkout.Session.retrieve(session_id)
    session_order_id = (session.metadata or {}).get("order_id") or getattr(session, "client_reference_id", None)
    if session_order_id != order_id:
        return False, "order_mismatch"
    if session.payment_status != "paid":
        return False, "not_paid"
    set_status(order_id, "paid", session_id)
    return True, session


@app.get("/api/checkout-status")
def checkout_status():
    order_id = request.args.get("order_id", "")
    session_id = request.args.get("session_id", "")
    ok, result = verify_paid(order_id, session_id)
    if not ok:
        code = 503 if result == "payment_verification_not_configured" else 402
        return jsonify({"paid": False, "error": result}), code
    return jsonify({"paid": True, "order_id": order_id})


@app.get("/api/order-by-session")
def order_by_session():
    session_id = str(request.args.get("session_id", "")).strip()
    if not session_id.startswith("cs_") or len(session_id) < 20:
        return jsonify({"error": "invalid_session_id"}), 400
    order = get_order_by_session(session_id)
    if not order:
        return jsonify({"found": False}), 404
    return jsonify({
        "found": True,
        "order_id": order["id"],
        "status": order["status"],
    })


@app.get("/api/qa-review-by-session")
def qa_review_by_session():
    """Temporary, synthetic-order-only QA endpoint. Never exposes real customer orders."""
    session_id = str(request.args.get("session_id", "")).strip()
    if not session_id:
        return jsonify({"error": "session_id_required"}), 400
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT id, email, child_name, payload, status, generated_text
            FROM orders
            WHERE stripe_session_id=:session_id
            LIMIT 1
        """), {"session_id": session_id}).mappings().first()
    if not row:
        return jsonify({"error": "order_not_found"}), 404
    if row["email"] != "quest-test@example.com" or row["child_name"] != "TestEmma":
        return jsonify({"error": "synthetic_test_only"}), 403
    return jsonify({
        "order_id": row["id"],
        "status": row["status"],
        "payload": json.loads(row["payload"]),
        "generated_text": row["generated_text"],
    })


@app.get("/api/qa-review-testemma")
def qa_review_testemma():
    """Temporary synthetic QA endpoint for the single TestEmma order."""
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT id, email, child_name, payload, status, generated_text
            FROM orders
            WHERE email='quest-test@example.com' AND child_name='TestEmma'
            ORDER BY updated_at DESC
            LIMIT 1
        """)).mappings().first()
    if not row:
        return jsonify({"error": "synthetic_order_not_found"}), 404
    return jsonify({
        "order_id": row["id"],
        "status": row["status"],
        "payload": json.loads(row["payload"]),
        "generated_text": row["generated_text"],
    })


@app.post("/api/generate")
def generate():
    if OpenAI is None or not os.getenv("OPENAI_API_KEY"):
        return jsonify({"error": "generation_not_configured"}), 503

    data = request.get_json(silent=True) or {}
    order_id = str(data.get("order_id", ""))
    session_id = str(data.get("session_id", ""))
    ok, result = verify_paid(order_id, session_id)
    if not ok:
        return jsonify({"error": result}), 402

    order = get_order(order_id)
    payload = json.loads(order["payload"])
    prompt = f"""Du bist Autor und Spieldesigner für hochwertige, sichere Kindergeburtstage.
Erstelle ein vollständig spielbares, personalisiertes Geburtstags-Abenteuer mit genau 8 Stationen und etwa 45–60 Minuten Spielzeit.

Daten:
Geburtstagskind: {payload['child_name']}
Alter: {payload['age']}
Gruppengröße: {payload['group_size']}
Interessen: {payload['interests']}
Lesestufe: {payload.get('reading_level','kurze_saetze')}
Rechnen: {payload.get('math_level','altersgerecht')}
Kniffligkeit: {payload.get('difficulty','ausgewogen')}
Bewegung: {payload.get('activity_level','ausgewogen')}
Gewünschte Dauer: {payload.get('desired_duration','45')} Minuten
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
- Schwierigkeit an Lesestufe, Rechenniveau, gewünschte Kniffligkeit und Dauer anpassen.
- Nur erlaubte Orte verwenden.
- Kein Feuer, keine Elektrizität, keine Straße, kein gefährliches Klettern, keine scharfen Gegenstände, keine verschlossenen Räume.
- Keine bekannten Franchise-Figuren oder geschützten Welten.
- Keine Lebensmittel als zwingende Mechanik.
- Lösungen eindeutig und altersgerecht.

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

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    response = client.responses.create(model=model, input=prompt)
    generated = response.output_text

    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE orders SET generated_text=:generated_text, status='generated', updated_at=:updated_at
            WHERE id=:id
        """), {"generated_text": generated, "updated_at": now_iso(), "id": order_id})

    return jsonify({"order_id": order_id, "status": "generated", "content": generated})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
