import base64
import hashlib
import html
import io
import json
import os

import requests
from openai import OpenAI
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PUZZLE_TYPES = ["Logik", "Beobachtung", "Bewegung", "Kooperation", "Code", "Wort", "Zahlen", "Suche"]

QUEST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "subtitle": {"type": "string"},
        "parent_summary": {"type": "string"},
        "setup_minutes": {"type": "integer"},
        "materials": {"type": "array", "items": {"type": "string"}},
        "preparation": {
            "type": "array", "minItems": 8, "maxItems": 8,
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "station": {"type": "integer"}, "location": {"type": "string"},
                    "hide": {"type": "string"}, "item": {"type": "string"},
                },
                "required": ["station", "location", "hide", "item"],
            },
        },
        "intro_story": {"type": "string"},
        "stations": {
            "type": "array", "minItems": 8, "maxItems": 8,
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "number": {"type": "integer"}, "title": {"type": "string"},
                    "current_location": {"type": "string"}, "story": {"type": "string"},
                    "child_card": {"type": "string"}, "task": {"type": "string"},
                    "puzzle_type": {"type": "string"}, "puzzle_visual": {"type": "string"},
                    "team_role": {"type": "string"}, "difficulty": {"type": "string"},
                    "solution": {"type": "string"}, "next_location": {"type": "string"},
                    "hint": {"type": "string"}, "second_hint": {"type": "string"},
                    "duration_minutes": {"type": "integer"},
                },
                "required": [
                    "number", "title", "current_location", "story", "child_card", "task",
                    "puzzle_type", "puzzle_visual", "team_role", "difficulty", "solution",
                    "next_location", "hint", "second_hint", "duration_minutes",
                ],
            },
        },
        "finale": {"type": "string"},
        "rain_backup": {"type": "string"},
        "certificate_text": {"type": "string"},
        "bonus_game": {
            "type": "object", "additionalProperties": False,
            "properties": {"title": {"type": "string"}, "instructions": {"type": "string"}},
            "required": ["title", "instructions"],
        },
        "route_check": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title", "subtitle", "parent_summary", "setup_minutes", "materials", "preparation",
        "intro_story", "stations", "finale", "rain_backup", "certificate_text", "bonus_game", "route_check",
    ],
}


def build_prompt(payload, qa_feedback=""):
    locations = payload.get("locations") or []
    feedback = f"\nKORRIGIERE DIESE QA-PUNKTE:\n{qa_feedback}\n" if qa_feedback else ""
    return f"""Du bist Autor, Rätseldesigner und Qualitätsprüfer für ein Premium-Produkt für Kindergeburtstage.
Erstelle eine vollständig spielbare personalisierte GeburtstagsQuest mit GENAU 8 Stationen und ca. 45-60 Minuten Spielzeit.
Die Käuferin soll denken: ausdrucken, Karten verstecken, losspielen. Ziel-Aufbauzeit: höchstens 15-20 Minuten.

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

PREMIUM-QUALITÄTSREGELN
- Genau 8 Stationen, Nummern 1 bis 8. Station 8 führt zum Finale.
- current_location ist der Ort, AN DEM die Stationskarte liegt. next_location ist das Ziel nach dem gelösten Rätsel.
- Verwende ausschließlich erlaubte Orte und respektiere Tabu-Orte strikt.
- Die Route muss logisch und eindeutig sein.
- child_card ist vollständig selbständig spielbar: Geschichte UND alle nötigen Anweisungen stehen dort. Eltern sollen nichts ergänzen müssen.
- task ist nur die knappe Elternbeschreibung derselben Aufgabe.
- Für {payload.get('age', '')}-Jährige: spannend und altersgerecht, weder Vorschulniveau noch Schulaufgaben-Gefühl; pro Rätsel ca. 3-7 Minuten.
- Mindestens 5 verschiedene puzzle_type aus: {', '.join(PUZZLE_TYPES)}.
- Mindestens 4 Stationen enthalten in puzzle_visual eine druckbare visuelle Komponente: Buchstabenraster, Zahlenfolge, Code-Tabelle, ASCII-Muster oder Suchfeld. Max. 12 Zeilen und ca. 32 Zeichen je Zeile; nur Standardzeichen.
- Keine Spezialkenntnisse; jede Lösung eindeutig.
- Zwei Hilfestufen: hint ist sanft; second_hint führt deutlich näher zur Lösung, ohne die Antwort direkt zu verraten.
- team_role beteiligt die Gruppe und verhindert, dass immer das schnellste Kind alles löst. Rollen abwechseln.
- difficulty ist leicht, mittel oder knifflig. Beginne nicht mit der schwierigsten Station.
- Höchstens 6 unterschiedliche Zusatzmaterialien, möglichst Papier, Stift, Klebeband; keine aufwendigen Bastelarbeiten.
- setup_minutes muss realistisch <= 20 sein.
- Sicherheit: kein Feuer, Strom, Straßenverkehr, gefährliches Klettern, scharfe Gegenstände, verschlossene Räume oder zwingende Lebensmittel.
- Keine Franchise-Figuren, Markenwelten oder urheberrechtlich geschützten Charaktere.
- rain_backup ist ein kurzer praktischer Schlechtwetter-Plan; wenn die Route ohnehin innen ist, sage das knapp.
- Finale emotional und feierlich; Urkunde enthält den Vornamen.
- route_check nennt konkrete Aufbauchecks, keine Floskeln.
- Warm, fantasievoll, kompakt, professionell; niemals erwähnen, dass KI verwendet wurde.
{feedback}"""


def validate_quest(data, payload):
    issues = []
    stations = data.get("stations") or []
    if len(stations) != 8:
        return ["Es müssen genau 8 Stationen sein."]
    if [s.get("number") for s in stations] != list(range(1, 9)):
        issues.append("Stationsnummern müssen exakt 1 bis 8 sein.")
    if (data.get("setup_minutes") or 999) > 20:
        issues.append("Aufbauzeit muss höchstens 20 Minuten sein.")
    if len({str(s.get("puzzle_type", "")).strip().lower() for s in stations}) < 5:
        issues.append("Mindestens 5 unterschiedliche Rätseltypen verwenden.")
    if sum(1 for s in stations if str(s.get("puzzle_visual", "")).strip()) < 4:
        issues.append("Mindestens 4 Stationen brauchen eine visuelle Rätselkomponente.")
    durations = [int(s.get("duration_minutes") or 0) for s in stations]
    if sum(durations) < 32 or sum(durations) > 55:
        issues.append("Stationszeiten sollten zusammen etwa 32-55 Minuten ergeben.")
    for i, s in enumerate(stations, start=1):
        if len(str(s.get("child_card", "")).strip()) < 120:
            issues.append(f"Station {i}: Kinderkarte ist zu knapp und wahrscheinlich nicht selbständig spielbar.")
        for key in ["current_location", "next_location", "team_role", "hint", "second_hint"]:
            if not str(s.get(key, "")).strip():
                issues.append(f"Station {i}: {key} fehlt.")
    if len(data.get("preparation") or []) != 8:
        issues.append("Vorbereitungsliste muss genau 8 Stationen enthalten.")
    return issues


def generate_quest(payload):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=240.0)
    model = os.getenv("OPENAI_MODEL", "gpt-6-luna")
    feedback = ""
    last_issues = []
    for _ in range(2):
        response = client.responses.create(
            model=model,
            input=build_prompt(payload, feedback),
            reasoning={"effort": "low"},
            max_output_tokens=11000,
            text={"format": {"type": "json_schema", "name": "geburtstagsquest_premium", "schema": QUEST_SCHEMA, "strict": True}, "verbosity": "medium"},
        )
        data = json.loads(response.output_text)
        last_issues = validate_quest(data, payload)
        if not last_issues:
            return json.dumps(data, ensure_ascii=False)
        feedback = "\n".join(f"- {x}" for x in last_issues)
    raise RuntimeError("Quest quality gate failed: " + "; ".join(last_issues[:8]))


def _safe(value):
    return html.escape(str(value or "")).replace("\n", "<br/>")


def _schedule(st, legacy):
    rows = [
        ["Beispielzeit", "Programmpunkt", "Hinweis"],
        ["15:00", "Ankommen & freies Spiel", "10-20 Min. Puffer für verspätete Gäste"],
        ["15:20", "Kuchen / Snacks", "Danach kurz Toilette und Getränke"],
        ["15:45", "Einstiegsgeschichte", "Alle Kinder sammeln, Karte 1 bereithalten"],
        ["15:50", "GeburtstagsQuest", "Ca. 45-60 Min.; Tipps nur bei Bedarf"],
        ["16:40", "Finale & Schatz", "Schatz gemeinsam öffnen"],
        ["16:50", "Bonusspiel / freies Spiel", "Flexibler Puffer bis zum Abholen"],
    ]
    data = [[Paragraph(f"<b>{_safe(x)}</b>", st["small"]) for x in rows[0]]]
    data += [[Paragraph(_safe(x), st["small"]) for x in row] for row in rows[1:]]
    t = Table(data, colWidths=[27 * mm, 57 * mm, 84 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), legacy.PURPLE), ("TEXTCOLOR", (0, 0), (-1, 0), legacy.WHITE),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D8D0DE")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _child_card(station, st, legacy):
    mono = ParagraphStyle("premium_mono", fontName="Courier-Bold", fontSize=10.5, leading=13, textColor=legacy.INK)
    role = f"<b>Teamrolle:</b> {_safe(station.get('team_role'))} &nbsp;&nbsp; <b>Schwierigkeit:</b> {_safe(station.get('difficulty'))}"
    flow = [
        Paragraph("KINDERKARTE - AUSSCHNEIDEN", st["small"]),
        Paragraph(f"Station {station.get('number')}: {_safe(station.get('title'))}", st["card_title"]),
        Paragraph(role, st["body"]),
        HRFlowable(width="100%", thickness=1, color=legacy.GOLD, spaceBefore=3, spaceAfter=8),
        Paragraph(_safe(station.get("child_card")), st["card_body"]),
    ]
    visual = str(station.get("puzzle_visual") or "").strip()
    if visual:
        flow += [Spacer(1, 4), Preformatted(visual, mono)]
    flow += [Spacer(1, 6), Paragraph("Wenn ihr feststeckt: Fragt die Spielleitung nach Tipp 1.", st["small"])]
    t = Table([[flow]], colWidths=[164 * mm], hAlign="CENTER")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white), ("BOX", (0, 0), (-1, -1), 1.4, legacy.PURPLE),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 12), ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    return t


def structured_pdf_bytes(quest, payload, legacy):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=legacy.A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=str(quest.get("title") or "GeburtstagsQuest"), author="GeburtstagsQuest")
    st = legacy.styles()
    story = [Spacer(1, 20 * mm), Paragraph("GEBURTSTAGSQUEST", st["cover_brand"]), Paragraph(_safe(quest.get("title")), st["cover_title"]),
             Paragraph(_safe(quest.get("subtitle")), st["cover_sub"]), Spacer(1, 5 * mm)]
    meta = [
        ["Für", payload.get("child_name")], ["Alter", f"{payload.get('age')} Jahre"], ["Gruppe", f"{payload.get('group_size')} Kinder"],
        ["Thema", payload.get("theme")], ["Spielzeit", "ca. 45-60 Minuten"], ["Aufbau", f"ca. {quest.get('setup_minutes')} Minuten"],
    ]
    mt = Table([[Paragraph(f"<b>{_safe(a)}</b>", st["small"]), Paragraph(_safe(b), st["body"])] for a, b in meta], colWidths=[34 * mm, 104 * mm], hAlign="CENTER")
    mt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), legacy.WARM), ("BOX", (0, 0), (-1, -1), 1, legacy.GOLD),
                            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DED5C5")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [mt, Spacer(1, 10 * mm), Paragraph("Vorbereiten. Karten verstecken. Losspielen.", st["cover_sub"]), PageBreak()]

    story += [Paragraph("Schnellstart für Eltern", st["h1"]), Paragraph(_safe(quest.get("parent_summary")), st["body"]),
              legacy.labeled_box("15-Minuten-Ziel", "Drucke die Kinderkarten aus, schneide sie aus und verstecke sie gemäß Vorbereitungstabelle. Lösungen und Tipps bleiben bei dir.", st, colors.HexColor("#DDEBDD")),
              Spacer(1, 5 * mm), Paragraph("Material", st["h2"])]
    story += [Paragraph("- " + _safe(x), st["body"]) for x in quest.get("materials") or []]
    story += [Spacer(1, 3 * mm), Paragraph("Beispiel-Ablauf für einen entspannten Geburtstag", st["h2"]), _schedule(st, legacy), PageBreak()]

    story += [Paragraph("Vorbereitung - genau so verstecken", st["h1"])]
    prep = [[Paragraph("<b>Nr.</b>", st["small"]), Paragraph("<b>Ort der Karte</b>", st["small"]), Paragraph("<b>Verstecken / vorbereiten</b>", st["small"]), Paragraph("<b>Material</b>", st["small"])]]
    for r in quest.get("preparation") or []:
        prep.append([Paragraph(str(r.get("station", "")), st["small"]), Paragraph(_safe(r.get("location")), st["small"]), Paragraph(_safe(r.get("hide")), st["small"]), Paragraph(_safe(r.get("item")), st["small"])])
    pt = Table(prep, colWidths=[13 * mm, 40 * mm, 75 * mm, 40 * mm], repeatRows=1)
    pt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), legacy.PURPLE), ("TEXTCOLOR", (0, 0), (-1, 0), legacy.WHITE),
                            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D8D0DE")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [pt, Spacer(1, 7 * mm), legacy.labeled_box("Schlechtwetter-Plan", quest.get("rain_backup"), st, colors.HexColor("#E4EFF8")), PageBreak()]

    story += [Paragraph("Spielleitung - Lösungen & Tipps", st["h1"]), Paragraph("Diese Seiten bleiben bei den Erwachsenen. Die Kinder erhalten nur die späteren Kinderkarten.", st["body"])]
    for s in quest.get("stations") or []:
        info = (f"Ort der Karte: {s.get('current_location', '')}\nRätseltyp: {s.get('puzzle_type', '')} | Schwierigkeit: {s.get('difficulty', '')} | Zeit: {s.get('duration_minutes', '')} Min.\n"
                f"Aufgabe: {s.get('task', '')}\nLösung: {s.get('solution', '')}\nDanach: {s.get('next_location', '')}\nTipp 1: {s.get('hint', '')}\nTipp 2: {s.get('second_hint', '')}")
        story.append(KeepTogether([Paragraph(f"Station {s.get('number')}: {_safe(s.get('title'))}", st["h2"]), legacy.labeled_box("Spielleitung", info, st, legacy.WARM), Spacer(1, 4 * mm)]))
    story.append(PageBreak())

    story += [Paragraph("Einstiegsgeschichte", st["h1"]), legacy.labeled_box("Zum Vorlesen", quest.get("intro_story"), st, legacy.WARM), Spacer(1, 7 * mm),
              Paragraph("Danach übergibst du direkt Kinderkarte 1 oder lässt sie am ersten Ort finden.", st["small"]), PageBreak(),
              Paragraph("KINDERKARTEN", st["cover_title"]), Paragraph("Ab hier beginnt der Teil für die Kinder. Jede Karte ist vollständig spielbar und kann einzeln ausgeschnitten bzw. versteckt werden.", st["cover_sub"]), PageBreak()]
    for s in quest.get("stations") or []:
        story += [Spacer(1, 7 * mm), _child_card(s, st, legacy), PageBreak()]

    story += [Paragraph("FINALE - ZUM VORLESEN", st["h1"]), legacy.labeled_box("Finale", quest.get("finale"), st, legacy.WARM), Spacer(1, 8 * mm),
              Paragraph("10-Minuten-Bonus", st["h2"]), Paragraph(f"<b>{_safe((quest.get('bonus_game') or {}).get('title'))}</b>", st["body"]),
              Paragraph(_safe((quest.get("bonus_game") or {}).get("instructions")), st["body"]), PageBreak(), Paragraph("Qualitätscheck vor dem Start", st["h1"])]
    story += [Paragraph("- " + _safe(x), st["body"]) for x in quest.get("route_check") or []]
    story += [Spacer(1, 6 * mm), legacy.labeled_box("Schnelltest", "Gehe die Route einmal ohne Kinder ab. Prüfe, ob jede Karte am richtigen Ort liegt und ob Station 8 wirklich zum Schatz führt.", st, colors.HexColor("#DDEBDD")), PageBreak(),
              Spacer(1, 25 * mm), Paragraph("URKUNDE", st["certificate_title"]), HRFlowable(width="65%", thickness=2, color=legacy.GOLD, hAlign="CENTER", spaceBefore=4, spaceAfter=16),
              Paragraph(_safe(quest.get("certificate_text")), st["certificate_body"]), Spacer(1, 14 * mm), Paragraph("Mission geschafft - Rätsel gelöst - Schatz gefunden", st["cover_sub"]), Spacer(1, 20 * mm),
              Table([["____________________________", "____________________________"], ["Datum", "Unterschrift"]], colWidths=[70 * mm, 70 * mm], hAlign="CENTER", style=TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("TEXTCOLOR", (0, 1), (-1, 1), legacy.MUTED), ("FONTSIZE", (0, 1), (-1, 1), 8)]))]
    doc.build(story, onFirstPage=legacy.footer, onLaterPages=legacy.footer)
    return buffer.getvalue()


def install(legacy):
    legacy.QUEST_SCHEMA = QUEST_SCHEMA
    legacy.build_prompt = build_prompt
    legacy.generate_quest = generate_quest
    legacy.validate_quest = validate_quest
    legacy.structured_pdf_bytes = lambda quest, payload: structured_pdf_bytes(quest, payload, legacy)

    def send_email(to_email, pdf_bytes, order_id):
        from_email = os.environ["RESEND_FROM_EMAIL"]
        test_recipient = os.getenv("RESEND_TEST_RECIPIENT", "").strip()
        recipient = test_recipient if "resend.dev" in from_email.lower() and test_recipient else to_email
        content_hash = hashlib.sha256(pdf_bytes).hexdigest()[:16]
        payload = {
            "from": from_email, "to": [recipient], "subject": "Deine GeburtstagsQuest ist fertig",
            "html": "<p>Hallo,</p><p>deine personalisierte GeburtstagsQuest ist fertig.</p><p>Im Anhang findest du Eltern-Schnellstart, Aufbauplan, Lösungen, vollständig spielbare Kinderkarten, Finale, Bonusspiel und Urkunde.</p><p>Viel Spaß bei eurem Abenteuer!</p><p>GeburtstagsQuest</p>",
            "attachments": [{"filename": f"GeburtstagsQuest-{order_id}.pdf", "content": base64.b64encode(pdf_bytes).decode("ascii"), "content_type": "application/pdf"}],
        }
        r = requests.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}", "Content-Type": "application/json", "Idempotency-Key": f"geburtstagsquest-{order_id}-{content_hash}"}, json=payload, timeout=60)
        if not r.ok:
            raise RuntimeError(f"Resend HTTP {r.status_code}: {r.text[:500]}")
        return r.json()

    legacy.send_email = send_email
