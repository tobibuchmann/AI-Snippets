import base64
import hashlib
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
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
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

PURPLE = colors.HexColor("#4B2A74")
PURPLE_DARK = colors.HexColor("#2D1845")
GOLD = colors.HexColor("#E2B354")
WARM = colors.HexColor("#F8F3EA")
LAVENDER = colors.HexColor("#EEE6F7")
INK = colors.HexColor("#2B2830")
MUTED = colors.HexColor("#706A76")
WHITE = colors.white


QUEST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "subtitle": {"type": "string"},
        "parent_summary": {"type": "string"},
        "materials": {"type": "array", "items": {"type": "string"}},
        "preparation": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "station": {"type": "integer"},
                    "location": {"type": "string"},
                    "hide": {"type": "string"},
                    "item": {"type": "string"},
                },
                "required": ["station", "location", "hide", "item"],
            },
        },
        "intro_story": {"type": "string"},
        "stations": {
            "type": "array",
            "minItems": 8,
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "number": {"type": "integer"},
                    "title": {"type": "string"},
                    "story": {"type": "string"},
                    "child_card": {"type": "string"},
                    "task": {"type": "string"},
                    "solution": {"type": "string"},
                    "next_location": {"type": "string"},
                    "hint": {"type": "string"},
                    "duration_minutes": {"type": "integer"},
                },
                "required": [
                    "number", "title", "story", "child_card", "task",
                    "solution", "next_location", "hint", "duration_minutes",
                ],
            },
        },
        "finale": {"type": "string"},
        "certificate_text": {"type": "string"},
        "bonus_game": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "instructions": {"type": "string"},
            },
            "required": ["title", "instructions"],
        },
        "route_check": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title", "subtitle", "parent_summary", "materials", "preparation",
        "intro_story", "stations", "finale", "certificate_text",
        "bonus_game", "route_check",
    ],
}


def now_utc():
    return datetime.now(timezone.utc)


def now_iso():
    return now_utc().isoformat()


def get_order(order_id):
    if not engine:
        return None
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT * FROM orders WHERE id=:id"), {"id": order_id}
        ).mappings().first()
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


def reset_order_for_regeneration(order_id):
    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE orders
            SET status='paid',
                generated_text=NULL,
                updated_at=:updated_at
            WHERE id=:id
            RETURNING id
        """), {"updated_at": now_iso(), "id": order_id}).first()
        return result is not None


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
    return f"""Du bist Autor, Rätseldesigner und Qualitätsprüfer für hochwertige Kindergeburtstage.
Erstelle eine vollständig spielbare, personalisierte GeburtstagsQuest für Eltern mit GENAU 8 Stationen und insgesamt ca. 45–60 Minuten Spielzeit.

DATEN
Geburtstagskind: {payload.get('child_name', '')}
Alter: {payload.get('age', '')}
Gruppengröße: {payload.get('group_size', '')}
Interessen: {payload.get('interests', '')}
Thema: {payload.get('theme', '')}
Spielbereich: {payload.get('play_area', '')}
Erlaubte Orte: {', '.join(locations)}
Weitere erlaubte Orte: {payload.get('other_locations', '')}
Tabu-Orte: {payload.get('forbidden_locations', '')}
Gewünschtes Finale: {payload.get('final_location', '')}
Besondere Hinweise: {payload.get('notes', '')}

QUALITÄTSREGELN
- Genau 8 Stationen. Nummeriere sie 1 bis 8.
- Jede Station muss eindeutig zur nächsten führen; Station 8 führt zum Finale.
- Verwende nur erlaubte Orte und respektiere Tabu-Orte strikt.
- Variiere die Mechaniken: Logik, Beobachtung, Bewegung, Kooperation, Code, Wort- und Zahlenrätsel.
- Rätsel müssen ohne Spezialwissen lösbar, altersgerecht und eindeutig sein.
- Schreibe auf jeder Station eine kurze Kinderkarte, die direkt vorgelesen oder ausgedruckt werden kann.
- Die Elternlösung muss klar sagen, was die richtige Lösung ist und was als Nächstes passiert.
- Gib pro Station einen kleinen Tipp an, der das Rätsel nicht sofort verrät.
- Plane pro Station realistische Minuten; zusammen mit Einstieg/Finale ca. 45–60 Minuten.
- Keine gefährlichen Aufgaben: kein Feuer, Strom, Straßenverkehr, gefährliches Klettern, scharfe Gegenstände, verschlossene Räume.
- Keine zwingenden Lebensmittelmechaniken.
- Keine bekannten Franchise-Figuren, Markenwelten oder urheberrechtlich geschützten Charaktere.
- Formuliere warm, fantasievoll und konkret, aber nicht unnötig lang.
- Die Vorbereitungsliste muss für Eltern praktisch sein: wo etwas hingelegt/versteckt wird und welches Material nötig ist.
- Die Urkunde soll den Vornamen des Geburtstagskindes enthalten.
- Prüfe am Ende die Route und nenne etwaige Aufbauhinweise in route_check.
"""


def generate_quest(payload):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=240.0)
    model = os.getenv("OPENAI_MODEL", "gpt-6-luna")
    response = client.responses.create(
        model=model,
        input=build_prompt(payload),
        reasoning={"effort": "low"},
        max_output_tokens=9000,
        text={
            "format": {
                "type": "json_schema",
                "name": "geburtstagsquest",
                "description": "Strukturierte, druckfertige GeburtstagsQuest mit genau acht Stationen.",
                "schema": QUEST_SCHEMA,
                "strict": True,
            },
            "verbosity": "medium",
        },
    )
    data = json.loads(response.output_text)
    if len(data.get("stations", [])) != 8:
        raise RuntimeError("Quest generation did not return exactly 8 stations")
    return json.dumps(data, ensure_ascii=False)


def parse_quest(content):
    try:
        data = json.loads(content)
    except Exception:
        return None
    if isinstance(data, dict) and isinstance(data.get("stations"), list):
        return data
    return None


def safe(value):
    return html.escape(str(value or "")).replace("\n", "<br/>")


def footer(canvas, doc):
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(colors.HexColor("#D9D2DE"))
    canvas.setLineWidth(0.4)
    canvas.line(18 * mm, 13 * mm, width - 18 * mm, 13 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(18 * mm, 8 * mm, "GeburtstagsQuest · Nur für den privaten Gebrauch")
    canvas.drawRightString(width - 18 * mm, 8 * mm, f"Seite {doc.page}")
    canvas.restoreState()


def styles():
    base = getSampleStyleSheet()
    return {
        "cover_brand": ParagraphStyle(
            "cover_brand", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=13, leading=16, textColor=GOLD, alignment=TA_CENTER, spaceAfter=12,
        ),
        "cover_title": ParagraphStyle(
            "cover_title", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=28, leading=32, textColor=PURPLE_DARK, alignment=TA_CENTER, spaceAfter=12,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", parent=base["BodyText"], fontSize=13, leading=18,
            textColor=INK, alignment=TA_CENTER, spaceAfter=16,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=20, leading=24, textColor=PURPLE_DARK, spaceBefore=4, spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=14, leading=18, textColor=PURPLE, spaceBefore=8, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontSize=10.5, leading=15,
            textColor=INK, spaceAfter=7,
        ),
        "small": ParagraphStyle(
            "small", parent=base["BodyText"], fontSize=8.8, leading=12,
            textColor=MUTED, spaceAfter=4,
        ),
        "card_title": ParagraphStyle(
            "card_title", parent=base["Heading3"], fontName="Helvetica-Bold",
            fontSize=12, leading=15, textColor=PURPLE_DARK, spaceAfter=5,
        ),
        "card_body": ParagraphStyle(
            "card_body", parent=base["BodyText"], fontSize=11, leading=16,
            textColor=INK, spaceAfter=2,
        ),
        "certificate_title": ParagraphStyle(
            "certificate_title", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=26, leading=31, textColor=PURPLE_DARK, alignment=TA_CENTER, spaceAfter=14,
        ),
        "certificate_body": ParagraphStyle(
            "certificate_body", parent=base["BodyText"], fontSize=14, leading=21,
            textColor=INK, alignment=TA_CENTER, spaceAfter=12,
        ),
    }


def labeled_box(label, content, st, background=LAVENDER):
    data = [[
        Paragraph(f"<b>{safe(label)}</b><br/>{safe(content)}", st["body"])
    ]]
    table = Table(data, colWidths=[168 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("BOX", (0, 0), (-1, -1), 0.7, PURPLE),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def structured_pdf_bytes(quest, payload):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=str(quest.get("title") or "GeburtstagsQuest"),
        author="GeburtstagsQuest",
    )
    st = styles()
    story = []

    story += [
        Spacer(1, 24 * mm),
        Paragraph("GEBURTSTAGSQUEST", st["cover_brand"]),
        Paragraph(safe(quest.get("title")), st["cover_title"]),
        Paragraph(safe(quest.get("subtitle")), st["cover_sub"]),
        Spacer(1, 6 * mm),
    ]
    meta = [
        [Paragraph("<b>Für</b>", st["small"]), Paragraph(safe(payload.get("child_name")), st["body"])],
        [Paragraph("<b>Alter</b>", st["small"]), Paragraph(f"{safe(payload.get('age'))} Jahre", st["body"])],
        [Paragraph("<b>Gruppe</b>", st["small"]), Paragraph(f"{safe(payload.get('group_size'))} Kinder", st["body"])],
        [Paragraph("<b>Thema</b>", st["small"]), Paragraph(safe(payload.get("theme")), st["body"])],
        [Paragraph("<b>Dauer</b>", st["small"]), Paragraph("ca. 45–60 Minuten", st["body"])],
    ]
    meta_table = Table(meta, colWidths=[34 * mm, 104 * mm], hAlign="CENTER")
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WARM),
        ("BOX", (0, 0), (-1, -1), 1, GOLD),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DED5C5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [meta_table, Spacer(1, 12 * mm)]
    story += [Paragraph(
        "Dein persönliches Abenteuer: vorbereiten, ausdrucken, verstecken – und losspielen.",
        st["cover_sub"],
    ), PageBreak()]

    story += [
        Paragraph("Schnellstart für Eltern", st["h1"]),
        Paragraph(safe(quest.get("parent_summary")), st["body"]),
        HRFlowable(width="100%", thickness=1, color=GOLD, spaceBefore=4, spaceAfter=10),
        Paragraph("Material", st["h2"]),
    ]
    materials = quest.get("materials") or []
    for item in materials:
        story.append(Paragraph("• " + safe(item), st["body"]))

    story += [Spacer(1, 4), Paragraph("Vorbereitung", st["h2"])]
    prep_rows = [[
        Paragraph("<b>Station</b>", st["small"]),
        Paragraph("<b>Ort</b>", st["small"]),
        Paragraph("<b>Verstecken / vorbereiten</b>", st["small"]),
        Paragraph("<b>Material</b>", st["small"]),
    ]]
    for row in quest.get("preparation") or []:
        prep_rows.append([
            Paragraph(str(row.get("station", "")), st["small"]),
            Paragraph(safe(row.get("location")), st["small"]),
            Paragraph(safe(row.get("hide")), st["small"]),
            Paragraph(safe(row.get("item")), st["small"]),
        ])
    prep_table = Table(prep_rows, colWidths=[16 * mm, 37 * mm, 75 * mm, 40 * mm], repeatRows=1)
    prep_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D8D0DE")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [prep_table, PageBreak()]

    story += [
        Paragraph("Einstiegsgeschichte", st["h1"]),
        labeled_box("Zum Vorlesen", quest.get("intro_story"), st, background=WARM),
        Spacer(1, 8 * mm),
        Paragraph(
            "Tipp: Lies die Geschichte erst vor, wenn alle Kinder bereit sind. Danach startet direkt Station 1.",
            st["small"],
        ),
        PageBreak(),
    ]

    stations = quest.get("stations") or []
    for station in stations:
        number = station.get("number", "")
        story += [
            Paragraph(f"Station {number}: {safe(station.get('title'))}", st["h1"]),
            Table([[
                Paragraph(f"<b>Ort</b><br/>{safe(station.get('next_location'))}", st["small"]),
                Paragraph(f"<b>Zeit</b><br/>{safe(station.get('duration_minutes'))} Min.", st["small"]),
            ]], colWidths=[120 * mm, 48 * mm], style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), WARM),
                ("BOX", (0, 0), (-1, -1), 0.5, GOLD),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ])),
            Spacer(1, 5 * mm),
            Paragraph("Geschichte", st["h2"]),
            Paragraph(safe(station.get("story")), st["body"]),
            Spacer(1, 2 * mm),
            labeled_box("KINDERKARTE – ausschneiden oder vorlesen", station.get("child_card"), st, background=LAVENDER),
            Spacer(1, 5 * mm),
            Paragraph("Aufgabe", st["h2"]),
            Paragraph(safe(station.get("task")), st["body"]),
            KeepTogether([
                labeled_box("Elternlösung", station.get("solution"), st, background=WARM),
                Spacer(1, 3 * mm),
                labeled_box("Tipp, falls es hakt", station.get("hint"), st, background=colors.HexColor("#F5F0FA")),
            ]),
            PageBreak(),
        ]

    story += [
        Paragraph("Das Finale", st["h1"]),
        labeled_box("Zum Vorlesen", quest.get("finale"), st, background=WARM),
        Spacer(1, 8 * mm),
        Paragraph("10-Minuten-Bonus", st["h2"]),
        Paragraph(f"<b>{safe((quest.get('bonus_game') or {}).get('title'))}</b>", st["body"]),
        Paragraph(safe((quest.get("bonus_game") or {}).get("instructions")), st["body"]),
        PageBreak(),
    ]

    story += [Paragraph("Lösungsübersicht", st["h1"])]
    solution_rows = [[
        Paragraph("<b>Nr.</b>", st["small"]),
        Paragraph("<b>Station</b>", st["small"]),
        Paragraph("<b>Lösung</b>", st["small"]),
        Paragraph("<b>Weiter zu</b>", st["small"]),
    ]]
    for s in stations:
        solution_rows.append([
            Paragraph(str(s.get("number", "")), st["small"]),
            Paragraph(safe(s.get("title")), st["small"]),
            Paragraph(safe(s.get("solution")), st["small"]),
            Paragraph(safe(s.get("next_location")), st["small"]),
        ])
    sol_table = Table(solution_rows, colWidths=[13 * mm, 42 * mm, 75 * mm, 38 * mm], repeatRows=1)
    sol_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D8D0DE")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [sol_table, Spacer(1, 7 * mm), Paragraph("Route prüfen", st["h2"])]
    for check in quest.get("route_check") or []:
        story.append(Paragraph("✓ " + safe(check), st["body"]))
    story.append(PageBreak())

    story += [
        Spacer(1, 25 * mm),
        Paragraph("URKUNDE", st["certificate_title"]),
        HRFlowable(width="65%", thickness=2, color=GOLD, hAlign="CENTER", spaceBefore=4, spaceAfter=16),
        Paragraph(safe(quest.get("certificate_text")), st["certificate_body"]),
        Spacer(1, 14 * mm),
        Paragraph("Mission geschafft · Rätsel gelöst · Schatz gefunden", st["cover_sub"]),
        Spacer(1, 20 * mm),
        Table([["____________________________", "____________________________"],
               ["Datum", "Unterschrift"]], colWidths=[70 * mm, 70 * mm], hAlign="CENTER",
              style=TableStyle([
                  ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                  ("TEXTCOLOR", (0, 1), (-1, 1), MUTED),
                  ("FONTSIZE", (0, 1), (-1, 1), 8),
              ])),
    ]

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def legacy_markdown_pdf_bytes(title, content):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=title, author="GeburtstagsQuest",
    )
    st = styles()
    story = [Paragraph(safe(title), st["cover_title"]), Spacer(1, 6)]
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 5))
        elif line.startswith("# "):
            story.append(Paragraph(safe(line[2:]), st["h1"]))
        elif line.startswith("## "):
            story.append(Paragraph(safe(line[3:]), st["h2"]))
        elif line.startswith("### "):
            story.append(Paragraph(f"<b>{safe(line[4:])}</b>", st["body"]))
        elif line.startswith("---"):
            story.append(PageBreak())
        elif line.startswith("- "):
            story.append(Paragraph("• " + safe(line[2:]), st["body"]))
        else:
            story.append(Paragraph(safe(line), st["body"]))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def quest_pdf_bytes(payload, generated):
    quest = parse_quest(generated)
    if quest:
        return structured_pdf_bytes(quest, payload)
    return legacy_markdown_pdf_bytes(
        f"GeburtstagsQuest für {payload.get('child_name', '')}", generated
    )


def send_email(to_email, pdf_bytes, order_id):
    from_email = os.environ["RESEND_FROM_EMAIL"]
    test_recipient = os.getenv("RESEND_TEST_RECIPIENT", "").strip()
    actual_recipient = test_recipient if "resend.dev" in from_email.lower() and test_recipient else to_email
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()[:16]
    payload = {
        "from": from_email,
        "to": [actual_recipient],
        "subject": "Deine GeburtstagsQuest ist fertig",
        "html": (
            "<p>Hallo,</p>"
            "<p>deine personalisierte GeburtstagsQuest ist fertig.</p>"
            "<p>Im Anhang findest du das druckfertige Elternheft mit Geschichte, "
            "8 Stationen, Lösungen, Finale und Urkunde.</p>"
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
            "Idempotency-Key": f"geburtstagsquest-{order_id}-{content_hash}",
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
        pdf_bytes = quest_pdf_bytes(payload, generated)
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
        "openai_model": os.getenv("OPENAI_MODEL", "gpt-6-luna"),
        "structured_quest_output": True,
        "resend_configured": bool(os.getenv("RESEND_API_KEY") and os.getenv("RESEND_FROM_EMAIL")),
        "resend_test_recipient_override": bool(os.getenv("RESEND_TEST_RECIPIENT")),
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


@app.post("/admin/regenerate/<order_id>")
def admin_regenerate(order_id):
    token = os.getenv("ADMIN_TOKEN", "")
    supplied = request.headers.get("X-Admin-Token", "")
    if not token or not supplied or supplied != token:
        return jsonify({"error": "unauthorized"}), 401
    if not get_order(order_id):
        return jsonify({"error": "order_not_found"}), 404
    if not reset_order_for_regeneration(order_id):
        return jsonify({"error": "reset_failed"}), 500
    queue_fulfillment(order_id)
    return jsonify({"queued": True, "order_id": order_id})


def regenerate_legacy_test_order():
    time.sleep(12)
    order_id = os.getenv("TEST_REGENERATE_ORDER", "").strip()
    if not order_id or not engine:
        return
    try:
        order = get_order(order_id)
        if not order:
            app.logger.warning("Test regeneration skipped: order not found")
            return
        if order.get("generated_text") and parse_quest(order["generated_text"]):
            app.logger.warning("Test regeneration skipped: structured quest already present")
            return
        app.logger.warning("Starting one-time structured test regeneration for order=%s", order_id)
        if reset_order_for_regeneration(order_id):
            queue_fulfillment(order_id)
    except Exception:
        app.logger.exception("One-time test regeneration failed")


threading.Thread(target=recover_stale_jobs, daemon=True).start()
threading.Thread(target=regenerate_legacy_test_order, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
