import json
import os
import re
import threading
import time

from openai import OpenAI

from premium_pdf import structured_pdf_bytes

PUZZLE_TYPES = ["code", "logic", "observation", "movement", "teamwork", "word", "number", "search"]

QUEST_SCHEMA = {
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
            "type": "array", "minItems": 8, "maxItems": 8,
            "items": {
                "type": "object", "additionalProperties": False,
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
            "type": "array", "minItems": 8, "maxItems": 8,
            "items": {
                "type": "object", "additionalProperties": False,
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
                    "number", "title", "current_location", "next_location", "story",
                    "child_card", "puzzle_type", "puzzle_display", "task", "solution",
                    "hint_1", "hint_2", "team_role", "duration_minutes",
                ],
            },
        },
        "finale": {"type": "string"},
        "audio_finale": {"type": "string"},
        "certificate_text": {"type": "string"},
        "bonus_game": {
            "type": "object", "additionalProperties": False,
            "properties": {"title": {"type": "string"}, "instructions": {"type": "string"}},
            "required": ["title", "instructions"],
        },
        "route_check": {"type": "array", "items": {"type": "string"}},
        "quality_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title", "subtitle", "parent_summary", "setup_minutes", "party_schedule",
        "materials", "indoor_fallback", "preparation", "intro_story", "audio_intro", "stations",
        "finale", "audio_finale", "certificate_text", "bonus_game", "route_check", "quality_notes",
    ],
}


def _allowed_locations(payload):
    values = list(payload.get("locations") or [])
    other = str(payload.get("other_locations") or "").strip()
    if other:
        values += [x.strip() for x in re.split(r"[,;\n]", other) if x.strip()]
    final = str(payload.get("final_location") or "").strip()
    if final:
        values.append(final)
    return values


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def adaptive_profile(payload):
    age = max(6, min(10, _int(payload.get("age"), 8)))
    age_profiles = {
        6: "Ein-Schritt-Aufgaben, sehr kurze Texte, viele Symbole und einfache Muster; keine langen Codes.",
        7: "Kurze Ein- bis Zwei-Schritt-Aufgaben, einfache Wörter, klare Muster und erste kurze Codes.",
        8: "Zwei-Schritt-Aufgaben, kurze Geheimcodes, visuelle Logik und einfache Schlussfolgerungen.",
        9: "Mehrstufige, aber kompakte Aufgaben, Geheimschrift, Logik, Beobachtung und kleine Kombinationsrätsel.",
        10: "Kniffligere Zwei- bis Drei-Schritt-Aufgaben mit Kombinationslogik, ohne Schulprüfungscharakter.",
    }
    reading = {
        "vorlesen": "Lesen darf nicht Voraussetzung für die Lösung sein. Text extrem kurz und visuell unterstützen.",
        "kurze_saetze": "Kurze, klare Sätze; keine langen Fließtexte auf Kinderkarten.",
        "sicher": "Kurze Wortspiele, Codes und Textindizien sind möglich.",
    }.get(str(payload.get("reading_level") or ""), "Textmenge automatisch altersgerecht halten.")
    math = {
        "ohne": "Keine Rechenaufgaben. Zahlen nur als Code, Reihenfolge oder Zählhilfe.",
        "bis20": "Rechnen höchstens im Zahlenraum bis 20 und nur spielerisch.",
        "bis100": "Einfache Rechnungen bis 100 höchstens in einer Station.",
        "altersgerecht": "Rechnen altersgerecht und höchstens in einer Station; kein Arbeitsblatt-Stil.",
    }.get(str(payload.get("math_level") or ""), "Rechnen altersgerecht und sparsam einsetzen.")
    difficulty = {
        "leicht": "Viele frühe Erfolgserlebnisse; klare Lösungswege.",
        "ausgewogen": "Mischung aus schnellen Erfolgen und 2-3 echten Aha-Momenten.",
        "knifflig": "Mehr Kombinationsaufgaben, aber weiterhin ohne Spezialwissen und mit eindeutiger Lösung.",
    }.get(str(payload.get("difficulty") or ""), "Ausgewogene Schwierigkeit.")
    activity = {
        "ruhig": "Bewegung sparsam; Schwerpunkt Beobachtung, Suchen, Codes und Teamlogik.",
        "ausgewogen": "Ruhige Denkaufgaben und aktive Such-/Bewegungsstationen abwechseln.",
        "viel": "Mindestens drei aktive Such-/Bewegungsstationen, ohne Rennen, Klettern oder riskante Aktionen.",
    }.get(str(payload.get("activity_level") or ""), "Ruhige und aktive Stationen ausgewogen abwechseln.")
    return "\n".join([
        f"ALTER: {age_profiles[age]}",
        f"LESEN: {reading}",
        f"RECHNEN: {math}",
        f"KN IFFLIGKEIT: {difficulty}".replace("KN I", "KNI"),
        f"AKTIVITÄT: {activity}",
    ])


def build_prompt(payload, feedback=""):
    age = max(6, min(10, _int(payload.get("age"), 8)))
    locations = _allowed_locations(payload)
    target_duration = _int(payload.get("desired_duration"), 45)
    if target_duration not in {30, 45, 60}:
        target_duration = 45
    correction = f"\nKORRIGIERE DIESE QUALITÄTSPUNKTE:\n{feedback}\n" if feedback else ""
    return f"""Du entwickelst ein PREMIUM-PARTY-KIT für einen Kindergeburtstag. Es muss so gut sein, dass Eltern dafür 39 Euro bezahlen.
Ziel: maximal wenig Elternstress, höchstens etwa 10 Minuten Aufbau, ungefähr {target_duration} Minuten Spielspaß, echte Personalisierung und ein Wow-Effekt für {age}-Jährige.

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
Gewünschte Dauer: ca. {target_duration} Minuten
Besondere Hinweise: {payload.get('notes','')}

ADAPTIVES NIVEAUPROFIL
{adaptive_profile(payload)}

PREMIUM-REGELN
- GENAU 8 Stationen; Einstieg, Stationen und Finale zusammen ungefähr {target_duration} Minuten.
- setup_minutes realistisch <= 10. Nutze überwiegend Papier, Stifte und Alltagsgegenstände.
- Jede Station nennt current_location UND next_location. Station 8 führt zum Finale.
- child_card MUSS alleine spielbar sein: kurze Story + vollständige Aufgabe + alles, was Kinder wissen müssen.
- puzzle_display enthält den tatsächlich druckbaren Rätselinhalt. Keine bloße Beschreibung dessen, was Eltern noch selbst erstellen sollen.
- Nutze mindestens 6 unterschiedliche puzzle_type-Werte aus: {', '.join(PUZZLE_TYPES)}. Kein Typ häufiger als zweimal.
- Enthalten sein müssen mindestens eine Beobachtungs-, eine Bewegungs-, eine Such- und eine Code- oder Logikstation.
- Mindestens 3 Stationen müssen echte Kooperation erfordern. team_role vergibt wechselnde Rollen.
- Pro Station zwei konkrete Hinweise: hint_1 sanft, hint_2 deutlich. Lösung immer eindeutig.
- Personalisierung soll in Einstieg und mindestens 4 Stationen Interessen/Name sinnvoll aufgreifen.
- indoor_fallback: konkrete Ersatzlösung für wetterabhängige Stationen, ohne neue Materialien.
- party_schedule: 5-6 konkrete Zeitblöcke relativ zum Partybeginn.
- preparation: GENAU 8 Zeilen, eine pro Station, mit konkretem Ort, Versteck und Material.
- Keine gefährlichen Aufgaben, kein Feuer, Strom, Straßenverkehr, gefährliches Klettern, scharfe Gegenstände oder verschlossene Räume.
- Keine zwingenden Lebensmittel, keine Marken- oder Franchise-Figuren.
- Verwende nur erlaubte Orte; Tabu-Orte strikt vermeiden.
- route_check bestätigt Reihenfolge, Orte, Finale und Aufbau. quality_notes dokumentiert 5-8 kurze Selbstchecks.
- Sprache warm, spannend, knapp. Kein KI-Jargon, kein Schul-Arbeitsblatt-Ton.
- audio_intro: 80-130 Wörter, direkt an {payload.get('child_name','das Geburtstagskind')} und das Team gerichtet; spannender Missionsstart, passend zum Thema und mindestens einem Interesse. Keine Regieanweisungen.
- audio_finale: 60-100 Wörter, persönliche Gratulation, greift die Mission auf und nennt das Geburtstagskind. Keine Regieanweisungen.
{correction}"""


def quality_gate(data, payload):
    errors, warnings = [], []
    stations = data.get("stations") or []
    if len(stations) != 8:
        errors.append("Es müssen genau 8 Stationen vorhanden sein.")
    if [s.get("number") for s in stations] != list(range(1, 9)):
        errors.append("Stationsnummern müssen exakt 1 bis 8 sein.")
    if int(data.get("setup_minutes") or 999) > 10:
        errors.append("Aufbauzeit liegt über 10 Minuten.")

    target = _int(payload.get("desired_duration"), 45)
    if target not in {30, 45, 60}:
        target = 45
    duration_bands = {30: (18, 28), 45: (28, 42), 60: (40, 55)}
    low, high = duration_bands[target]
    durations = [int(s.get("duration_minutes") or 0) for s in stations]
    station_minutes = sum(durations)
    if station_minutes < low or station_minutes > high:
        warnings.append(f"Stationszeit {station_minutes} Min. passt nur bedingt zum Ziel {target} Min.")

    type_list = [s.get("puzzle_type") for s in stations]
    types = set(type_list)
    if len(types) < 6:
        errors.append("Zu wenig Rätselvielfalt: mindestens 6 Typen erforderlich.")
    for puzzle_type in types:
        if puzzle_type and type_list.count(puzzle_type) > 2:
            errors.append(f"Rätseltyp {puzzle_type} kommt öfter als zweimal vor.")
    if "observation" not in types:
        errors.append("Mindestens eine Beobachtungsstation erforderlich.")
    if "movement" not in types:
        errors.append("Mindestens eine Bewegungsstation erforderlich.")
    if "search" not in types:
        errors.append("Mindestens eine Suchstation erforderlich.")
    if not ({"code", "logic"} & types):
        errors.append("Mindestens eine Code- oder Logikstation erforderlich.")

    teamwork = sum(1 for s in stations if s.get("puzzle_type") == "teamwork" or any(k in (s.get("team_role") or "").lower() for k in ["team", "gemeinsam", "sprecher", "wächter", "leser", "sucher", "chef"]))
    if teamwork < 3:
        errors.append("Mindestens 3 kooperative Stationen erforderlich.")
    for i, station in enumerate(stations, 1):
        if not str(station.get("child_card") or "").strip() or not str(station.get("puzzle_display") or "").strip():
            errors.append(f"Station {i} ist nicht druckfertig.")
        if not str(station.get("hint_1") or "").strip() or not str(station.get("hint_2") or "").strip():
            errors.append(f"Station {i} benötigt zwei Hinweise.")
    if len(data.get("preparation") or []) != 8:
        errors.append("Vorbereitung muss genau 8 Stationen enthalten.")
    if len(data.get("party_schedule") or []) < 5:
        errors.append("Party-Zeitplan unvollständig.")
    if not data.get("indoor_fallback"):
        errors.append("Indoor-Plan B fehlt.")
    if len(str(data.get("audio_intro") or "").split()) < 45:
        errors.append("Audio-Einleitung fehlt oder ist zu kurz.")
    if len(str(data.get("audio_finale") or "").split()) < 30:
        errors.append("Audio-Finale fehlt oder ist zu kurz.")

    forbidden = [x.strip().lower() for x in re.split(r"[,;\n]", str(payload.get("forbidden_locations") or "")) if x.strip()]
    for i, station in enumerate(stations, 1):
        location_text = (str(station.get("current_location") or "") + " " + str(station.get("next_location") or "")).lower()
        if any(item in location_text for item in forbidden):
            errors.append(f"Station {i} verwendet einen Tabu-Ort.")
    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "puzzle_types": len(types),
            "team_stations": teamwork,
            "station_minutes": station_minutes,
            "target_minutes": target,
            "setup_minutes": data.get("setup_minutes"),
            "audio_story": True,
        },
    }


def generate_quest(payload):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=240.0)
    model = os.getenv("OPENAI_MODEL", "gpt-6-luna")
    feedback = ""
    last_gate = None
    for _ in range(2):
        response = client.responses.create(
            model=model,
            input=build_prompt(payload, feedback),
            reasoning={"effort": "medium"},
            max_output_tokens=16000,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "geburtstagsquest_premium",
                    "description": "Premium, druckfertiges Party-Kit mit acht Stationen.",
                    "schema": QUEST_SCHEMA,
                    "strict": True,
                },
                "verbosity": "medium",
            },
        )
        text = str(response.output_text or "").strip()
        if not text:
            feedback = "Antworte kompakter und direkt im verlangten JSON-Schema."
            continue
        data = json.loads(text)
        last_gate = quality_gate(data, payload)
        if last_gate["passed"]:
            data["quality_gate"] = last_gate
            return json.dumps(data, ensure_ascii=False)
        feedback = "\n".join(f"- {x}" for x in last_gate["errors"])
    raise RuntimeError("Quality gate failed: " + " | ".join((last_gate or {}).get("errors", [])[:8]))


def _one_time_regeneration(legacy):
    time.sleep(1)
    order_id = os.getenv("TEST_REGENERATE_ORDER", "").strip()
    if not order_id:
        return
    try:
        legacy.app.logger.warning("Starting one-time premium QA regeneration for order=%s", order_id)
        if legacy.reset_order_for_regeneration(order_id):
            legacy.queue_fulfillment(order_id)
    except Exception:
        legacy.app.logger.exception("One-time premium QA regeneration failed")


def install(legacy):
    legacy.generate_quest = generate_quest
    legacy.structured_pdf_bytes = structured_pdf_bytes
    threading.Thread(target=_one_time_regeneration, args=(legacy,), daemon=True).start()
