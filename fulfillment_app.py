import base64
import hashlib
import html
import io
import json
import os
import re
import threading
import time
from datetime import datetime, timezone, timedelta

import requests
from flask import Flask, jsonify, request
from openai import OpenAI
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
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
PALE_BLUE = colors.HexColor("#EAF4F8")
PALE_GREEN = colors.HexColor("#ECF6EE")
PALE_YELLOW = colors.HexColor("#FFF7DC")

PUZZLE_TYPES = ["code", "logic", "observation", "movement", "teamwork", "word", "number", "search"]

QUEST_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "title": {"type": "string"}, "subtitle": {"type": "string"},
        "parent_summary": {"type": "string"}, "setup_minutes": {"type": "integer"},
        "party_schedule": {"type": "array", "items": {"type": "string"}},
        "materials": {"type": "array", "items": {"type": "string"}},
        "indoor_fallback": {"type": "array", "items": {"type": "string"}},
        "preparation": {"type": "array", "minItems": 8, "maxItems": 8,
            "items": {"type": "object", "additionalProperties": False,
                "properties": {"station": {"type": "integer"}, "location": {"type": "string"}, "hide": {"type": "string"}, "item": {"type": "string"}},
                "required": ["station", "location", "hide", "item"]}},
        "intro_story": {"type": "string"},
        "stations": {"type": "array", "minItems": 8, "maxItems": 8,
            "items": {"type": "object", "additionalProperties": False,
                "properties": {
                    "number": {"type": "integer"}, "title": {"type": "string"},
                    "current_location": {"type": "string"}, "next_location": {"type": "string"},
                    "story": {"type": "string"}, "child_card": {"type": "string"},
                    "puzzle_type": {"type": "string", "enum": PUZZLE_TYPES}, "puzzle_display": {"type": "string"},
                    "task": {"type": "string"}, "solution": {"type": "string"},
                    "hint_1": {"type": "string"}, "hint_2": {"type": "string"},
                    "team_role": {"type": "string"}, "duration_minutes": {"type": "integer"}},
                "required": ["number", "title", "current_location", "next_location", "story", "child_card", "puzzle_type", "puzzle_display", "task", "solution", "hint_1", "hint_2", "team_role", "duration_minutes"]}},
        "finale": {"type": "string"}, "certificate_text": {"type": "string"},
        "bonus_game": {"type": "object", "additionalProperties": False,
            "properties": {"title": {"type": "string"}, "instructions": {"type": "string"}}, "required": ["title", "instructions"]},
        "route_check": {"type": "array", "items": {"type": "string"}},
        "quality_notes": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["title", "subtitle", "parent_summary", "setup_minutes", "party_schedule", "materials", "indoor_fallback", "preparation", "intro_story", "stations", "finale", "certificate_text", "bonus_game", "route_check", "quality_notes"]
}

def now_utc(): return datetime.now(timezone.utc)
def now_iso(): return now_utc().isoformat()

def get_order(order_id):
    if not engine: return None
    with engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM orders WHERE id=:id"), {"id": order_id}).mappings().first()
        return dict(row) if row else None

def update_order(order_id, status, generated_text=None, session_id=None):
    with engine.begin() as conn:
        conn.execute(text("""UPDATE orders SET status=:status, generated_text=COALESCE(:generated_text, generated_text), stripe_session_id=COALESCE(:session_id, stripe_session_id), updated_at=:updated_at WHERE id=:id"""), {"status": status, "generated_text": generated_text, "session_id": session_id, "updated_at": now_iso(), "id": order_id})

def reset_order_for_regeneration(order_id):
    with engine.begin() as conn:
        row = conn.execute(text("""UPDATE orders SET status='paid', generated_text=NULL, updated_at=:updated_at WHERE id=:id RETURNING id"""), {"updated_at": now_iso(), "id": order_id}).first()
        return row is not None

def claim_generation(order_id, session_id=None):
    stale_before = (now_utc() - timedelta(minutes=2)).isoformat()
    with engine.begin() as conn:
        row = conn.execute(text("""UPDATE orders SET status='generating', stripe_session_id=COALESCE(:session_id, stripe_session_id), updated_at=:updated_at WHERE id=:id AND generated_text IS NULL AND status <> 'delivered' AND (status <> 'generating' OR updated_at < :stale_before) RETURNING id"""), {"session_id": session_id, "updated_at": now_iso(), "stale_before": stale_before, "id": order_id}).first()
        return row is not None

def _allowed_locations(payload):
    vals = list(payload.get("locations") or [])
    other = str(payload.get("other_locations") or "").strip()
    if other: vals += [x.strip() for x in re.split(r"[,;\n]", other) if x.strip()]
    final = str(payload.get("final_location") or "").strip()
    if final: vals.append(final)
    return vals

def build_prompt(payload):
    locations = _allowed_locations(payload)
    age = int(payload.get("age") or 9)
    return f"""Du entwickelst ein PREMIUM-PARTY-KIT für einen Kindergeburtstag. Es muss so gut sein, dass Eltern dafür 39 Euro bezahlen.
Ziel: möglichst wenig Elternstress, 15-20 Minuten Aufbau, 45-60 Minuten selbsttragender Spielspaß, echte Personalisierung und ein Wow-Effekt für {age}-Jährige.

DATEN
Geburtstagskind: {payload.get('child_name','')}
Alter: {age}
Gruppengröße: {payload.get('group_size','')}
Interessen: {payload.get('interests','')}
Thema: {payload.get('theme','')}
Spielbereich: {payload.get('play_area','')}
Erlaubte Orte: {', '.join(locations)}
Tabu-Orte: {payload.get('forbidden_locations','')}
Finale/Schatz: {payload.get('final_location','')}
Hinweise: {payload.get('notes','')}

PREMIUM-REGELN
- GENAU 8 Stationen, insgesamt 45-60 Minuten inkl. Einstieg und Finale.
- setup_minutes realistisch <= 20. Nutze überwiegend Papier, Stifte und Alltagsgegenstände.
- Jede Station nennt current_location UND next_location. Station 8 führt zum Finale.
- child_card MUSS alleine spielbar sein: kurze Story + vollständige Aufgabe + alles, was Kinder wissen müssen. Eltern dürfen die Aufgabe nicht zusätzlich erklären müssen.
- puzzle_display enthält den tatsächlich druckbaren Rätselinhalt, z.B. Geheimcode, Symbolfolge, Zahlenreihe, Suchliste, Wortsalat oder Logikhinweise. Keine bloße Beschreibung dessen, was Eltern noch selbst erstellen sollen.
- Nutze mindestens 6 unterschiedliche puzzle_type-Werte aus: {', '.join(PUZZLE_TYPES)}.
- Mindestens 3 Stationen müssen echte Kooperation erfordern. team_role vergibt wechselnde Rollen, z.B. Codechef, Spurensucher, Zeitwächter, Kartenleser, Teamsprecher.
- Für 9-Jährige: nicht babyhaft, nicht schulisch. Aha-Momente, Geheimschrift, Logik, Beobachtung, Bewegung und Codes; keine Spezialkenntnisse.
- Pro Station zwei Hinweise: hint_1 sanft, hint_2 deutlich. Lösung immer eindeutig.
- Personalisierung soll in Geschichte und mindestens 4 Stationen Interessen/Name sinnvoll aufgreifen, nicht nur austauschen.
- indoor_fallback: konkrete Ersatzlösung für wetterabhängige Stationen, ohne neue Materialien.
- party_schedule: 5-6 konkrete Zeitblöcke relativ zum Partybeginn (z.B. +00:00 Ankommen), damit Eltern den Nachmittag planen können.
- preparation: GENAU 8 Zeilen, eine pro Station, mit konkretem Ort, Versteck und Material.
- Keine gefährlichen Aufgaben, kein Feuer/Strom/Straßenverkehr/Klettern/scharfe Gegenstände/verschlossene Räume.
- Keine zwingenden Lebensmittel, keine Marken- oder Franchise-Figuren.
- Verwende nur erlaubte Orte; Tabu-Orte strikt vermeiden.
- route_check bestätigt Reihenfolge, Orte, Finale und Aufbau. quality_notes dokumentiert 4-8 kurze Selbstchecks.
- Sprache warm, spannend, knapp. Kein KI-Jargon.
"""

def quality_gate(data, payload):
    errors, warnings = [], []
    stations = data.get("stations") or []
    if len(stations) != 8: errors.append("Es müssen genau 8 Stationen vorhanden sein.")
    if int(data.get("setup_minutes") or 999) > 20: errors.append("Aufbauzeit liegt über 20 Minuten.")
    durations = [int(s.get("duration_minutes") or 0) for s in stations]
    if sum(durations) < 32 or sum(durations) > 52: warnings.append(f"Stationszeit ungewöhnlich: {sum(durations)} Min.")
    types = {s.get("puzzle_type") for s in stations}
    if len(types) < 6: errors.append("Zu wenig Rätselvielfalt (<6 Typen).")
    teamwork = sum(1 for s in stations if s.get("puzzle_type") == "teamwork" or any(k in (s.get("team_role") or "").lower() for k in ["team", "gemeinsam", "sprecher", "wächter", "leser", "sucher"]))
    if teamwork < 3: errors.append("Mindestens 3 kooperative Stationen erforderlich.")
    for i, s in enumerate(stations, 1):
        if int(s.get("number") or -1) != i: errors.append(f"Stationsnummer {i} inkonsistent.")
        if not str(s.get("child_card") or "").strip() or not str(s.get("puzzle_display") or "").strip(): errors.append(f"Station {i} ist nicht druckfertig.")
        if not str(s.get("hint_1") or "").strip() or not str(s.get("hint_2") or "").strip(): errors.append(f"Station {i} benötigt zwei Hinweise.")
    if len(data.get("preparation") or []) != 8: errors.append("Vorbereitung muss 8 Stationen enthalten.")
    forbidden = [x.strip().lower() for x in re.split(r"[,;\n]", str(payload.get("forbidden_locations") or "")) if x.strip()]
    for i, s in enumerate(stations, 1):
        loc_text = (str(s.get("current_location") or "") + " " + str(s.get("next_location") or "")).lower()
        if any(f in loc_text for f in forbidden): errors.append(f"Station {i} verwendet einen Tabu-Ort.")
    if not data.get("indoor_fallback"): errors.append("Indoor-Plan B fehlt.")
    if len(data.get("party_schedule") or []) < 5: errors.append("Party-Zeitplan unvollständig.")
    return {"passed": not errors, "errors": errors, "warnings": warnings, "metrics": {"puzzle_types": len(types), "team_stations": teamwork, "station_minutes": sum(durations), "setup_minutes": data.get("setup_minutes")}}

def generate_quest(payload):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=240.0)
    response = client.responses.create(model=os.getenv("OPENAI_MODEL", "gpt-6-luna"), input=build_prompt(payload), reasoning={"effort": "medium"}, max_output_tokens=12000, text={"format": {"type": "json_schema", "name": "geburtstagsquest_premium", "description": "Premium, druckfertiges Party-Kit mit acht Stationen.", "schema": QUEST_SCHEMA, "strict": True}, "verbosity": "medium"})
    data = json.loads(response.output_text)
    gate = quality_gate(data, payload)
    if not gate["passed"]: raise RuntimeError("Quality gate failed: " + " | ".join(gate["errors"]))
    data["quality_gate"] = gate
    return json.dumps(data, ensure_ascii=False)

def parse_quest(content):
    try: data = json.loads(content)
    except Exception: return None
    return data if isinstance(data, dict) and isinstance(data.get("stations"), list) else None

def safe(v): return html.escape(str(v or "")).replace("\n", "<br/>")

def footer(canvas, doc):
    canvas.saveState(); width, _ = A4
    canvas.setStrokeColor(colors.HexColor("#D9D2DE")); canvas.line(18*mm, 13*mm, width-18*mm, 13*mm)
    canvas.setFillColor(MUTED); canvas.setFont("Helvetica", 8)
    canvas.drawString(18*mm, 8*mm, "GeburtstagsQuest · Dein persönliches Party-Kit")
    canvas.drawRightString(width-18*mm, 8*mm, f"Seite {doc.page}"); canvas.restoreState()

def styles():
    b = getSampleStyleSheet()
    return {"brand": ParagraphStyle("brand", parent=b["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=GOLD, alignment=TA_CENTER, spaceAfter=12), "title": ParagraphStyle("title", parent=b["Title"], fontName="Helvetica-Bold", fontSize=28, leading=32, textColor=PURPLE_DARK, alignment=TA_CENTER, spaceAfter=12), "sub": ParagraphStyle("sub", parent=b["BodyText"], fontSize=13, leading=18, textColor=INK, alignment=TA_CENTER, spaceAfter=16), "h1": ParagraphStyle("h1", parent=b["Heading1"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=PURPLE_DARK, spaceAfter=10), "h2": ParagraphStyle("h2", parent=b["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=PURPLE, spaceBefore=6, spaceAfter=6), "body": ParagraphStyle("body", parent=b["BodyText"], fontSize=10.5, leading=15, textColor=INK, spaceAfter=7), "small": ParagraphStyle("small", parent=b["BodyText"], fontSize=8.7, leading=12, textColor=MUTED, spaceAfter=4), "child": ParagraphStyle("child", parent=b["BodyText"], fontName="Helvetica-Bold", fontSize=12.2, leading=17, textColor=PURPLE_DARK, spaceAfter=5), "puzzle": ParagraphStyle("puzzle", parent=b["BodyText"], fontName="Courier-Bold", fontSize=12, leading=17, textColor=INK, alignment=TA_CENTER, spaceAfter=3), "cert": ParagraphStyle("cert", parent=b["Title"], fontName="Helvetica-Bold", fontSize=26, leading=31, textColor=PURPLE_DARK, alignment=TA_CENTER, spaceAfter=14)}

def box(label, content, st, bg=LAVENDER, style="body"):
    t = Table([[Paragraph(f"<b>{safe(label)}</b><br/>{safe(content)}", st[style])]], colWidths=[168*mm])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),bg),("BOX",(0,0),(-1,-1),0.8,PURPLE),("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),("TOPPADDING",(0,0),(-1,-1),9),("BOTTOMPADDING",(0,0),(-1,-1),9)])); return t

def theme_label(theme):
    t=(theme or "").lower()
    if "detektiv" in t: return "FALLAKTE · GEHEIM"
    if "weltraum" in t: return "MISSION · KOSMOS"
    if "dino" in t: return "EXPEDITION · URZEIT"
    if "zauber" in t: return "MAGISCHE MISSION"
    if "tier" in t: return "RETTUNGSMISSION"
    return "GEHEIMMISSION"

def structured_pdf_bytes(q, payload):
    buf=io.BytesIO(); doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=18*mm,bottomMargin=18*mm,title=str(q.get("title") or "GeburtstagsQuest"),author="GeburtstagsQuest"); st=styles(); story=[]
    story += [Spacer(1,20*mm), Paragraph(theme_label(payload.get("theme")), st["brand"]), Paragraph(safe(q.get("title")), st["title"]), Paragraph(safe(q.get("subtitle")), st["sub"])]
    meta=[["Für",payload.get("child_name")],["Alter",f"{payload.get('age')} Jahre"],["Team",f"{payload.get('group_size')} Kinder"],["Dauer","45-60 Minuten"],["Aufbau",f"ca. {q.get('setup_minutes')} Minuten"]]
    mt=Table([[Paragraph(f"<b>{safe(a)}</b>",st["small"]),Paragraph(safe(b),st["body"])] for a,b in meta],colWidths=[34*mm,104*mm],hAlign="CENTER"); mt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),WARM),("BOX",(0,0),(-1,-1),1,GOLD),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#DED5C5")),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),7)])); story += [mt, Spacer(1,10*mm), Paragraph("Ausdrucken · verstecken · losspielen", st["sub"]), PageBreak()]
    story += [Paragraph("Schnellstart für Eltern",st["h1"]),Paragraph(safe(q.get("parent_summary")),st["body"]),box("Qualitätsversprechen", "8 spielbare Stationen · zwei Hinweisstufen · Teamrollen · Indoor-Plan B · geprüfte Route",st,PALE_GREEN),Spacer(1,4*mm),Paragraph("Party-Zeitplan",st["h2"])]
    for x in q.get("party_schedule") or []: story.append(Paragraph("• "+safe(x),st["body"]))
    story += [Paragraph("Material",st["h2"])]
    for x in q.get("materials") or []: story.append(Paragraph("□ "+safe(x),st["body"]))
    story += [Paragraph("Schlechtwetter-Plan B",st["h2"])]
    for x in q.get("indoor_fallback") or []: story.append(Paragraph("• "+safe(x),st["body"]))
    story.append(PageBreak()); story += [Paragraph("Vorbereitung in 15-20 Minuten",st["h1"])]
    rows=[[Paragraph("<b>Nr.</b>",st["small"]),Paragraph("<b>Hier verstecken</b>",st["small"]),Paragraph("<b>Was tun?</b>",st["small"]),Paragraph("<b>Material</b>",st["small"])]]
    for r in q.get("preparation") or []: rows.append([Paragraph(str(r.get("station","")),st["small"]),Paragraph(safe(r.get("location")),st["small"]),Paragraph(safe(r.get("hide")),st["small"]),Paragraph(safe(r.get("item")),st["small"])])
    tb=Table(rows,colWidths=[14*mm,40*mm,73*mm,41*mm],repeatRows=1); tb.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),PURPLE),("TEXTCOLOR",(0,0),(-1,0),WHITE),("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#D8D0DE")),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),5)])); story += [tb,PageBreak(),Paragraph("Start der Mission",st["h1"]),box("Zum Vorlesen",q.get("intro_story"),st,WARM),PageBreak()]
    for s in q.get("stations") or []:
        n=s.get("number"); story += [Paragraph(f"KINDERKARTE {n} · {safe(s.get('title'))}",st["h1"]),Table([[Paragraph(f"<b>Gefunden bei</b><br/>{safe(s.get('current_location'))}",st["small"]),Paragraph(f"<b>Rätseltyp</b><br/>{safe(s.get('puzzle_type'))}",st["small"]),Paragraph(f"<b>Zeit</b><br/>{safe(s.get('duration_minutes'))} Min.",st["small"])]],colWidths=[72*mm,54*mm,42*mm],style=TableStyle([("BACKGROUND",(0,0),(-1,-1),WARM),("BOX",(0,0),(-1,-1),0.5,GOLD),("PADDING",(0,0),(-1,-1),6)])),Spacer(1,5*mm),box("MISSION",s.get("child_card"),st,LAVENDER,"child"),Spacer(1,4*mm),box("RÄTSEL",s.get("puzzle_display"),st,PALE_BLUE,"puzzle"),Spacer(1,4*mm),box("TEAMROLLE",s.get("team_role"),st,PALE_GREEN),Spacer(1,4*mm),Paragraph("Wenn ihr feststeckt, bittet den Spielleiter um Tipp 1 - erst danach um Tipp 2.",st["small"]),PageBreak(),Paragraph(f"ELTERNBLATT · Station {n}",st["h1"]),Paragraph(safe(s.get("story")),st["body"]),box("Aufgabe / Erwartung",s.get("task"),st,WARM),Spacer(1,3*mm),box("Lösung",s.get("solution"),st,PALE_GREEN),Spacer(1,3*mm),box("Tipp 1 · sanft",s.get("hint_1"),st,PALE_YELLOW),Spacer(1,3*mm),box("Tipp 2 · deutlich",s.get("hint_2"),st,colors.HexColor("#FBE8E8")),Spacer(1,3*mm),box("Danach geht es zu",s.get("next_location"),st,LAVENDER),PageBreak()]
    story += [Paragraph("Das Finale",st["h1"]),box("Zum Vorlesen",q.get("finale"),st,WARM),Spacer(1,7*mm),Paragraph("10-Minuten-Bonus",st["h2"]),Paragraph(f"<b>{safe((q.get('bonus_game') or {}).get('title'))}</b>",st["body"]),Paragraph(safe((q.get('bonus_game') or {}).get('instructions')),st["body"]),PageBreak(),Paragraph("Lösungen & Route auf einen Blick",st["h1"])]
    rows=[[Paragraph("<b>Nr.</b>",st["small"]),Paragraph("<b>Ort</b>",st["small"]),Paragraph("<b>Lösung</b>",st["small"]),Paragraph("<b>Weiter</b>",st["small"])]]
    for s in q.get("stations") or []: rows.append([Paragraph(str(s.get("number")),st["small"]),Paragraph(safe(s.get("current_location")),st["small"]),Paragraph(safe(s.get("solution")),st["small"]),Paragraph(safe(s.get("next_location")),st["small"])])
    tb=Table(rows,colWidths=[13*mm,42*mm,73*mm,40*mm],repeatRows=1); tb.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),PURPLE),("TEXTCOLOR",(0,0),(-1,0),WHITE),("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#D8D0DE")),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),5)])); story.append(tb); story += [Spacer(1,6*mm),Paragraph("Routencheck",st["h2"])]
    for x in q.get("route_check") or []: story.append(Paragraph("✓ "+safe(x),st["body"]))
    gate=q.get("quality_gate") or {}; metrics=gate.get("metrics") or {}; story += [box("Automatischer Qualitätscheck",f"Bestanden · {metrics.get('puzzle_types','?')} Rätseltypen · {metrics.get('team_stations','?')} Teamstationen · {metrics.get('station_minutes','?')} Stationsminuten · Aufbau {metrics.get('setup_minutes','?')} Min.",st,PALE_GREEN),PageBreak(),Spacer(1,24*mm),Paragraph("URKUNDE",st["cert"]),HRFlowable(width="65%",thickness=2,color=GOLD,hAlign="CENTER",spaceAfter=16),Paragraph(safe(q.get("certificate_text")),st["sub"]),Spacer(1,14*mm),Paragraph("Mission geschafft · Teamwork bewiesen · Schatz gefunden",st["sub"])]
    doc.build(story,onFirstPage=footer,onLaterPages=footer); return buf.getvalue()

def legacy_markdown_pdf_bytes(title,content):
    buf=io.BytesIO(); doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=18*mm,bottomMargin=18*mm,title=title,author="GeburtstagsQuest"); st=styles(); story=[Paragraph(safe(title),st["title"])]
    for line in content.splitlines():
        x=line.strip()
        if not x: story.append(Spacer(1,5))
        elif x.startswith("# "): story.append(Paragraph(safe(x[2:]),st["h1"]))
        elif x.startswith("## "): story.append(Paragraph(safe(x[3:]),st["h2"]))
        elif x.startswith("---"): story.append(PageBreak())
        elif x.startswith("- "): story.append(Paragraph("• "+safe(x[2:]),st["body"]))
        else: story.append(Paragraph(safe(x),st["body"]))
    doc.build(story,onFirstPage=footer,onLaterPages=footer); return buf.getvalue()

def quest_pdf_bytes(payload, generated):
    q=parse_quest(generated); return structured_pdf_bytes(q,payload) if q else legacy_markdown_pdf_bytes(f"GeburtstagsQuest für {payload.get('child_name','')}",generated)

def send_email(to_email,pdf_bytes,order_id):
    from_email=os.environ["RESEND_FROM_EMAIL"]; test_recipient=os.getenv("RESEND_TEST_RECIPIENT","").strip(); actual=test_recipient if "resend.dev" in from_email.lower() and test_recipient else to_email; h=hashlib.sha256(pdf_bytes).hexdigest()[:16]
    payload={"from":from_email,"to":[actual],"subject":"Deine persönliche GeburtstagsQuest ist fertig","html":"<p>Hallo,</p><p>dein persönliches GeburtstagsQuest Party-Kit ist fertig.</p><p>Im Anhang findest du Eltern-Schnellstart, Party-Zeitplan, 8 ausschneidbare Kinderkarten, zwei Hinweisstufen, Lösungen, Indoor-Plan B, Finale und Urkunde.</p><p>Viel Spaß bei eurem Abenteuer!</p><p>GeburtstagsQuest</p>","attachments":[{"filename":f"GeburtstagsQuest-{order_id}.pdf","content":base64.b64encode(pdf_bytes).decode("ascii"),"content_type":"application/pdf"}]}
    r=requests.post("https://api.resend.com/emails",headers={"Authorization":f"Bearer {os.environ['RESEND_API_KEY']}","Content-Type":"application/json","Idempotency-Key":f"geburtstagsquest-{order_id}-{h}"},json=payload,timeout=60)
    if not r.ok: raise RuntimeError(f"Resend HTTP {r.status_code}: {r.text[:500]}")
    return r.json()

def fulfill(order_id,session_id=None):
    order=get_order(order_id)
    if not order: raise ValueError("order_not_found")
    if order["status"]=="delivered": return {"status":"already_delivered"}
    payload=json.loads(order["payload"]); generated=order.get("generated_text")
    if not generated:
        if not claim_generation(order_id,session_id):
            latest=get_order(order_id)
            if latest and latest.get("generated_text"): generated=latest["generated_text"]
            else: return {"status":"generation_in_progress"}
        else:
            try: generated=generate_quest(payload); update_order(order_id,"generated",generated,session_id)
            except Exception: update_order(order_id,"fulfillment_failed",session_id=session_id); raise
    try:
        pdf=quest_pdf_bytes(payload,generated); result=send_email(order["email"],pdf,order_id); update_order(order_id,"delivered",generated,session_id); return {"status":"delivered","email_id":result.get("id")}
    except Exception: update_order(order_id,"delivery_failed",generated,session_id); raise

def run_fulfillment(order_id,session_id=None):
    try: result=fulfill(order_id,session_id); app.logger.warning("Fulfillment result order=%s status=%s",order_id,result.get("status"))
    except Exception: app.logger.exception("Fulfillment failed for %s",order_id)

def queue_fulfillment(order_id,session_id=None): threading.Thread(target=run_fulfillment,args=(order_id,session_id),daemon=True).start()
def stripe_webhook_secrets(): return [x for x in [os.getenv("FULFILLMENT_STRIPE_WEBHOOK_SECRET",""),os.getenv("FULFILLMENT_STRIPE_WEBHOOK_SECRET_TEST","")] if x]
def verify_stripe_event(raw,signature):
    last=None
    for secret in stripe_webhook_secrets():
        try: return stripe.Webhook.construct_event(raw,signature,secret)
        except Exception as e: last=e
    raise last or ValueError("no_webhook_secret")

def recover_stale_jobs():
    time.sleep(8)
    if not engine: return
    try:
        stale=(now_utc()-timedelta(minutes=2)).isoformat()
        with engine.begin() as conn: rows=conn.execute(text("""SELECT id,stripe_session_id FROM orders WHERE (status='delivery_failed' AND generated_text IS NOT NULL) OR (generated_text IS NULL AND status IN ('generating','fulfillment_failed') AND updated_at < :stale) ORDER BY updated_at ASC LIMIT 20"""),{"stale":stale}).mappings().all()
        for row in rows: queue_fulfillment(row["id"],row.get("stripe_session_id"))
    except Exception: app.logger.exception("Stale fulfillment recovery failed")

@app.get("/health")
def health(): return jsonify({"ok":True,"database_configured":bool(DATABASE_URL),"stripe_live_webhook_configured":bool(os.getenv("FULFILLMENT_STRIPE_WEBHOOK_SECRET")),"stripe_test_webhook_configured":bool(os.getenv("FULFILLMENT_STRIPE_WEBHOOK_SECRET_TEST")),"openai_configured":bool(os.getenv("OPENAI_API_KEY")),"openai_model":os.getenv("OPENAI_MODEL","gpt-6-luna"),"premium_quest_output":True,"quality_gate":True,"resend_configured":bool(os.getenv("RESEND_API_KEY") and os.getenv("RESEND_FROM_EMAIL"))})

@app.post("/stripe-webhook")
def stripe_webhook():
    if stripe is None or not stripe_webhook_secrets(): return jsonify({"error":"webhook_not_configured"}),503
    raw=request.get_data(cache=False,as_text=False); sig=request.headers.get("Stripe-Signature","")
    try: event=verify_stripe_event(raw,sig)
    except Exception: return jsonify({"error":"invalid_signature"}),400
    if event.get("type") not in {"checkout.session.completed","checkout.session.async_payment_succeeded"}: return jsonify({"received":True,"ignored":event.get("type")})
    session=event.get("data",{}).get("object",{})
    if session.get("payment_status")!="paid": return jsonify({"received":True,"payment_status":session.get("payment_status")})
    order_id=(session.get("metadata") or {}).get("order_id") or session.get("client_reference_id")
    if not order_id: return jsonify({"error":"order_id_missing"}),400
    queue_fulfillment(order_id,session.get("id")); return jsonify({"received":True,"queued":True})

@app.post("/admin/regenerate/<order_id>")
def admin_regenerate(order_id):
    token=os.getenv("ADMIN_TOKEN",""); supplied=request.headers.get("X-Admin-Token","")
    if not token or not supplied or supplied!=token: return jsonify({"error":"unauthorized"}),401
    if not get_order(order_id): return jsonify({"error":"order_not_found"}),404
    if not reset_order_for_regeneration(order_id): return jsonify({"error":"reset_failed"}),500
    queue_fulfillment(order_id); return jsonify({"queued":True,"order_id":order_id})

threading.Thread(target=recover_stale_jobs,daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))