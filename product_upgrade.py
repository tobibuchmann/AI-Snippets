import base64
import hashlib
import os
import re
from collections import Counter

import requests


PUZZLE_TYPES = ["code", "logic", "observation", "movement", "teamwork", "word", "number", "search"]

QUEST_SCHEMA_UPGRADED = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "subtitle": {"type": "string"},
        "parent_summary": {"type": "string"},
        "setup_minutes": {"type": "integer"},
        "party_schedule": {"type": "array", "items": {"type": "string"}},
        "materials": {"type": "array", "items": {"type": "string"}},
        "indoor_fallback": {"type": "array", "items": {"type": "string"}},
        "preparation": {
            "type": "array",
            "minItems": 8,
            "maxItems": 8,
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
        "audio_intro": {"type": "string"},
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
                    "current_location": {"type": "string"},
                    "next_location": {"type": "string"},
                    "story": {"type": "string"},
                    "child_card": {"type": "string"},
                    "puzzle_type": {"type": "string", "enum": PUZZLE_TYPES},
                    "puzzle_display": {"type": "string"},
                    "task": {"type": "string"},
                    "solution": {"type": "string"},
                    "hint_1": {"type": "string"},
                    "hint_2": {"type": "string"},
                    "team_role": {"type": "string"},
                    "duration_minutes": {"type": "integer"},
                },
                "required": [
                    "number",
                    "title",
                    "current_location",
                    "next_location",
                    "story",
                    "child_card",
                    "puzzle_type",
                    "puzzle_display",
                    "task",
                    "solution",
                    "hint_1",
                    "hint_2",
                    "team_role",
                    "duration_minutes",
                ],
            },
        },
        "finale": {"type": "string"},
        "audio_finale": {"type": "string"},
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
        "quality_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title",
        "subtitle",
        "parent_summary",
        "setup_minutes",
        "party_schedule",
        "materials",
        "indoor_fallback",
        "preparation",
        "intro_story",
        "audio_intro",
        "stations",
        "finale",
        "audio_finale",
        "certificate_text",
        "bonus_game",
        "route_check",
        "quality_notes",
    ],
}


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _allowed_locations(payload):
    vals = list(payload.get("locations") or [])
    other = str(payload.get("other_locations") or "").strip()
    if other:
        vals += [x.strip() for x in re.split(r"[,;\n]", other) if x.strip()]
    final = str(payload.get("final_location") or "").strip()
    if final:
        vals.append(final)
    return vals


def adaptive_profile(payload):
    age = max(6, min(10, _int(payload.get("age"), 8)))
    age_profiles = {
        6: "Ein-Schritt-Aufgaben, sehr kurze Texte, viele Symbole/Bilder, einfache Muster; keine langen Codes.",
        7: "Kurze Ein- bis Zwei-Schritt-Aufgaben, einfache Wörter, klare Muster und erste kurze Codes.",
        8: "Zwei-Schritt-Aufgaben, kurze Geheimcodes, visuelle Logik und einfache Schlussfolgerungen.",
        9: "Mehrstufige, aber kompakte Aufgaben, Geheimschrift, Logik, Beobachtung und kleine Kombinationsrätsel.",
        10: "Kniffligere Zwei- bis Drei-Schritt-Aufgaben mit Kombinationslogik, ohne Schulprüfungscharakter.",
    }
    reading_map = {
        "vorlesen": "Das Kind braucht beim Lesen Hilfe. Kinderkarten müssen visuell funktionieren; Text extrem kurz halten. Erwachsene dürfen die Story vorlesen, aber die eigentliche Lösung darf nicht von Lesekompetenz abhängen.",
        "kurze_saetze": "Das Kind liest kurze Sätze. Verwende kurze, klare Anweisungen und vermeide lange Fließtexte.",
        "sicher": "Das Kind liest sicher. Kurze Codes, Wortspiele und knappe Textindizien sind möglich.",
        "": "Passe Textmenge automatisch an das Alter an.",
    }
    math_map = {
        "ohne": "Keine Rechenaufgaben. Zahlen dürfen nur als Codes, Reihenfolge oder Zählhilfe vorkommen.",
        "bis20": "Rechnen höchstens im Zahlenraum bis 20 und nur spielerisch.",
        "bis100": "Einfache Rechnungen im Zahlenraum bis 100 sind möglich, aber höchstens in einer Station.",
        "altersgerecht": "Rechnen altersgerecht und höchstens in einer Station; keine schulischen Arbeitsblätter.",
        "": "Rechnen altersgerecht und sparsam einsetzen.",
    }
    difficulty_map = {
        "leicht": "Viele frühe Erfolgserlebnisse; jede Aufgabe in einem klaren Gedankenschritt lösbar.",
        "ausgewogen": "Mischung aus schnellen Erfolgen und 2-3 echten Aha-Momenten.",
        "knifflig": "Mehr Kombinationsaufgaben und Aha-Momente, aber weiterhin ohne Spezialwissen und mit eindeutiger Lösung.",
        "": "Ausgewogene Schwierigkeit mit einzelnen Aha-Momenten.",
    }
    activity_map = {
        "ruhig": "Bewegung sparsam; Schwerpunkt Beobachtung, Suchen, Codes und Teamlogik.",
        "ausgewogen": "Ruhige Denkaufgaben und aktive Such-/Bewegungsstationen abwechseln.",
        "viel": "Mindestens drei aktive Such-/Bewegungsstationen einbauen, ohne Rennen, Klettern oder riskante Aktionen.",
        "": "Ruhige und aktive Stationen ausgewogen abwechseln.",
    }
    reading = str(payload.get("reading_level") or "")
    math = str(payload.get("math_level") or "")
    difficulty = str(payload.get("difficulty") or "ausgewogen")
    activity = str(payload.get("activity_level") or "ausgewogen")
    return "\n".join(
        [
            f"ALTERSPROFIL: {age_profiles[age]}",
            f"LESEN: {reading_map.get(reading, reading_map[''])}",
            f"RECHNEN: {math_map.get(math, math_map[''])}",
            f"SCHWIERIGKEIT: {difficulty_map.get(difficulty, difficulty_map[''])}",
            f"AKTIVITÄT: {activity_map.get(activity, activity_map[''])}",
        ]
    )


def build_prompt(payload):
    locations = _allowed_locations(payload)
    age = max(6, min(10, _int(payload.get("age"), 8)))
    target_duration = _int(payload.get("desired_duration"), 45)
    if target_duration not in {30, 45, 60}:
        target_duration = 45

    return f"""Du entwickelst ein PREMIUM-PARTY-KIT für einen Kindergeburtstag.
Das Produkt soll Eltern maximal entlasten und sich spürbar genauer an die Kindergruppe anpassen als eine statische PDF-Schatzsuche.

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
Gewünschte Gesamtdauer: ca. {target_duration} Minuten
Besondere Wünsche: {payload.get('notes','')}

ADAPTIVES NIVEAUPROFIL
{adaptive_profile(payload)}

PRODUKTREGELN
- GENAU 8 Stationen. Einstieg, Stationen und Finale sollen zusammen ungefähr {target_duration} Minuten ergeben.
- setup_minutes realistisch <= 10. Die Eltern sollen im Wesentlichen nur drucken, Karten verstecken und den Schatz platzieren.
- Jede Station nennt current_location UND next_location. Station 8 führt zum Finale.
- child_card MUSS ohne zusätzliche Erklärung funktionieren: kurze Story + vollständige Aufgabe + alles Nötige.
- puzzle_display enthält den tatsächlich druckbaren Rätselinhalt. Keine Anweisung an Eltern, erst noch ein Rätsel zu basteln.
- Nutze mindestens 6 unterschiedliche puzzle_type-Werte aus: {', '.join(PUZZLE_TYPES)}.
- Kein puzzle_type häufiger als zweimal.
- Enthalten sein müssen: mindestens 1 observation, mindestens 1 movement, mindestens 1 search und mindestens 1 code ODER logic.
- Mindestens 3 Stationen erfordern echte Kooperation. team_role vergibt wechselnde Rollen.
- Vermeide monotone Folgen: nie mehr als zwei überwiegend text-/zahlenlastige Denkstationen hintereinander.
- Mische bewusst: Beobachten, Suchen, Bewegen, Kombinieren, Teamwork, Code/Logik und höchstens sparsam Wort/Zahl.
- Pro Station zwei Hinweise: hint_1 sanft, hint_2 deutlich. Lösung immer eindeutig.
- Prüfe jede Lösung darauf, dass es nicht zwei plausible Antworten gibt.
- Personalisierung muss in Einstieg und mindestens 4 Stationen Name, Interessen oder konkrete Partyangaben sinnvoll aufgreifen.
- indoor_fallback: konkrete Ersatzlösung für wetterabhängige Stationen, ohne neue Materialien.
- party_schedule: 5-6 Zeitblöcke relativ zum Partybeginn.
- preparation: GENAU 8 Zeilen, eine pro Station, mit Ort, Versteck und Material.
- Verwende nur erlaubte Orte; Tabu-Orte strikt vermeiden.
- Keine gefährlichen Aufgaben, kein Feuer/Strom/Straßenverkehr/Klettern/scharfe Gegenstände/verschlossene Räume.
- Keine zwingenden Lebensmittel, keine Marken- oder Franchise-Figuren.
- Sprache warm, spannend und knapp. Kein KI-Jargon, kein Schul-Arbeitsblatt-Ton.
- route_check bestätigt Reihenfolge, Orte, Finale und Aufbau.
- quality_notes dokumentiert 5-8 kurze Selbstchecks zu Alter, Lesbarkeit, Eindeutigkeit, Abwechslung, Dauer und Sicherheit.

PERSONALISIERTE AUDIO-STORY
- audio_intro: 80-130 Wörter, direkt an {payload.get('child_name','das Geburtstagskind')} und das Team gerichtet. Spannender Missionsstart, passend zum Thema und zu mindestens einem Interesse. Keine Regieanweisungen, keine Emojis.
- audio_finale: 60-100 Wörter. Persönliche Gratulation, greift die Mission auf und nennt das Geburtstagskind. Keine Regieanweisungen, keine Emojis.
- intro_story und finale bleiben zusätzlich als druckbare Textvarianten vollständig verständlich.
"""


def quality_gate(data, payload):
    errors, warnings = [], []
    stations = data.get("stations") or []

    if len(stations) != 8:
        errors.append("Es müssen genau 8 Stationen vorhanden sein.")
    if _int(data.get("setup_minutes"), 999) > 10:
        errors.append("Aufbauzeit liegt über 10 Minuten.")

    target = _int(payload.get("desired_duration"), 45)
    if target not in {30, 45, 60}:
        target = 45
    duration_bands = {30: (18, 27), 45: (28, 40), 60: (40, 54)}
    low, high = duration_bands[target]
    durations = [_int(s.get("duration_minutes"), 0) for s in stations]
    station_minutes = sum(durations)
    if station_minutes < low or station_minutes > high:
        warnings.append(
            f"Stationszeit {station_minutes} Min. passt nur bedingt zum Ziel {target} Min. (erwartet {low}-{high} Min.)."
        )

    types = [s.get("puzzle_type") for s in stations]
    distinct_types = set(types)
    counts = Counter(types)
    if len(distinct_types) < 6:
        errors.append("Zu wenig Rätselvielfalt (<6 Typen).")
    too_often = [t for t, n in counts.items() if t and n > 2]
    if too_often:
        errors.append("Ein Rätseltyp kommt öfter als zweimal vor: " + ", ".join(sorted(too_often)))
    if "observation" not in distinct_types:
        errors.append("Mindestens eine Beobachtungsstation erforderlich.")
    if "movement" not in distinct_types:
        errors.append("Mindestens eine Bewegungsstation erforderlich.")
    if "search" not in distinct_types:
        errors.append("Mindestens eine Suchstation erforderlich.")
    if not ({"code", "logic"} & distinct_types):
        errors.append("Mindestens eine Code- oder Logikstation erforderlich.")

    teamwork = sum(
        1
        for s in stations
        if s.get("puzzle_type") == "teamwork"
        or any(
            k in (s.get("team_role") or "").lower()
            for k in ["team", "gemeinsam", "sprecher", "wächter", "leser", "sucher", "chef"]
        )
    )
    if teamwork < 3:
        errors.append("Mindestens 3 kooperative Stationen erforderlich.")

    for i, station in enumerate(stations, 1):
        if _int(station.get("number"), -1) != i:
            errors.append(f"Stationsnummer {i} inkonsistent.")
        if not str(station.get("child_card") or "").strip() or not str(station.get("puzzle_display") or "").strip():
            errors.append(f"Station {i} ist nicht druckfertig.")
        if not str(station.get("hint_1") or "").strip() or not str(station.get("hint_2") or "").strip():
            errors.append(f"Station {i} benötigt zwei Hinweise.")

    if len(data.get("preparation") or []) != 8:
        errors.append("Vorbereitung muss 8 Stationen enthalten.")

    forbidden = [
        x.strip().lower()
        for x in re.split(r"[,;\n]", str(payload.get("forbidden_locations") or ""))
        if x.strip()
    ]
    for i, station in enumerate(stations, 1):
        loc_text = (
            str(station.get("current_location") or "")
            + " "
            + str(station.get("next_location") or "")
        ).lower()
        if any(item in loc_text for item in forbidden):
            errors.append(f"Station {i} verwendet einen Tabu-Ort.")

    if not data.get("indoor_fallback"):
        errors.append("Indoor-Plan B fehlt.")
    if len(data.get("party_schedule") or []) < 5:
        errors.append("Party-Zeitplan unvollständig.")
    if len(str(data.get("audio_intro") or "").split()) < 45:
        errors.append("Personalisierte Audio-Einleitung ist zu kurz oder fehlt.")
    if len(str(data.get("audio_finale") or "").split()) < 30:
        errors.append("Personalisiertes Audio-Finale ist zu kurz oder fehlt.")

    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "puzzle_types": len(distinct_types),
            "team_stations": teamwork,
            "station_minutes": station_minutes,
            "target_minutes": target,
            "setup_minutes": data.get("setup_minutes"),
            "audio_story": True,
        },
    }


def _tts_mp3(text, mood):
    body = {
        "model": os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
        "voice": os.getenv("OPENAI_TTS_VOICE", "coral"),
        "input": str(text).strip(),
        "instructions": (
            "Sprich auf Deutsch. "
            + mood
            + " Natürlich, warm und lebendig, wie eine hochwertige Hörspiel-Erzählung für einen Kindergeburtstag. "
            "Nicht übertrieben, nicht hektisch."
        ),
        "response_format": "mp3",
    }
    response = requests.post(
        "https://api.openai.com/v1/audio/speech",
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=120,
    )
    if not response.ok:
        raise RuntimeError(f"OpenAI TTS HTTP {response.status_code}: {response.text[:500]}")
    return response.content


def _send_email_with_audio(module, to_email, pdf_bytes, order_id):
    order = module.get_order(order_id) or {}
    quest = module.parse_quest(order.get("generated_text") or "") or {}

    audio_attachments = []
    try:
        if quest.get("audio_intro"):
            intro = _tts_mp3(
                quest["audio_intro"],
                "Der Beginn soll geheimnisvoll, einladend und erwartungsvoll klingen.",
            )
            audio_attachments.append(
                {
                    "filename": f"GeburtstagsQuest-{order_id}-Start.mp3",
                    "content": base64.b64encode(intro).decode("ascii"),
                    "content_type": "audio/mpeg",
                }
            )
        if quest.get("audio_finale"):
            finale = _tts_mp3(
                quest["audio_finale"],
                "Das Finale soll feierlich, stolz und fröhlich klingen.",
            )
            audio_attachments.append(
                {
                    "filename": f"GeburtstagsQuest-{order_id}-Finale.mp3",
                    "content": base64.b64encode(finale).decode("ascii"),
                    "content_type": "audio/mpeg",
                }
            )
    except Exception:
        module.app.logger.exception("Audio generation failed for order=%s; sending PDF without audio", order_id)
        audio_attachments = []

    from_email = os.environ["RESEND_FROM_EMAIL"]
    test_recipient = os.getenv("RESEND_TEST_RECIPIENT", "").strip()
    recipient_lower = str(to_email or "").strip().lower()
    reserved_test_domain = recipient_lower.endswith(("@example.com", "@example.org", "@example.net", ".test", ".invalid"))
    if reserved_test_domain:
        # Never try to deliver synthetic QA orders to reserved internet domains.
        # Resend's official sink accepts the request without emailing a real person.
        actual = test_recipient or "delivered@resend.dev"
    elif "resend.dev" in from_email.lower() and test_recipient:
        actual = test_recipient
    else:
        actual = to_email

    digest = hashlib.sha256(pdf_bytes)
    for attachment in audio_attachments:
        digest.update(attachment["content"].encode("ascii"))
    idem_hash = digest.hexdigest()[:16]

    attachments = [
        {
            "filename": f"GeburtstagsQuest-{order_id}.pdf",
            "content": base64.b64encode(pdf_bytes).decode("ascii"),
            "content_type": "application/pdf",
        }
    ] + audio_attachments

    audio_text = (
        "<p>Zusätzlich findest du zwei personalisierte Audio-Dateien für Missionsstart und Finale im Anhang. "
        "<strong>Hinweis:</strong> Die Stimmen sind KI-generiert und keine menschlichen Stimmen.</p>"
        if audio_attachments
        else ""
    )

    email_payload = {
        "from": from_email,
        "to": [actual],
        "subject": "Deine persönliche GeburtstagsQuest ist fertig",
        "html": (
            "<p>Hallo,</p>"
            "<p>dein persönliches GeburtstagsQuest Party-Kit ist fertig.</p>"
            "<p>Im PDF findest du Eltern-Schnellstart, Party-Zeitplan, 8 Kinderkarten, "
            "zwei Hinweisstufen, Lösungen, Indoor-Plan B, Finale und Urkunde.</p>"
            + audio_text
            + "<p>Viel Spaß bei eurem Abenteuer!</p><p>GeburtstagsQuest</p>"
        ),
        "attachments": attachments,
    }

    result = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
            "Content-Type": "application/json",
            "Idempotency-Key": f"geburtstagsquest-v2-{order_id}-{idem_hash}",
        },
        json=email_payload,
        timeout=60,
    )
    if not result.ok:
        raise RuntimeError(f"Resend HTTP {result.status_code}: {result.text[:500]}")
    return result.json()


def apply_upgrade(module):
    module.QUEST_SCHEMA = QUEST_SCHEMA_UPGRADED
    module.build_prompt = build_prompt
    module.quality_gate = quality_gate

    def send_email(to_email, pdf_bytes, order_id):
        return _send_email_with_audio(module, to_email, pdf_bytes, order_id)

    module.send_email = send_email
    module.app.config["GQ_PRODUCT_UPGRADE"] = "adaptive-v2-audio"
