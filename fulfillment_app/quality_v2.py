import json
import os
import re

from openai import OpenAI

from . import premium


CRITIC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "passed": {"type": "boolean"},
        "overall_issues": {"type": "array", "items": {"type": "string"}},
        "stations": {
            "type": "array",
            "minItems": 8,
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "number": {"type": "integer"},
                    "solvable": {"type": "boolean"},
                    "logically_correct": {"type": "boolean"},
                    "route_is_derivable": {"type": "boolean"},
                    "answer_not_leaked": {"type": "boolean"},
                    "hints_are_useful": {"type": "boolean"},
                    "age_appropriate": {"type": "boolean"},
                    "self_contained": {"type": "boolean"},
                    "issue": {"type": "string"},
                },
                "required": [
                    "number", "solvable", "logically_correct", "route_is_derivable",
                    "answer_not_leaked", "hints_are_useful", "age_appropriate",
                    "self_contained", "issue"
                ],
            },
        },
        "route_chain_valid": {"type": "boolean"},
        "personalization_strong": {"type": "boolean"},
        "team_roles_varied": {"type": "boolean"},
        "stories_varied": {"type": "boolean"},
        "preparation_concrete": {"type": "boolean"},
    },
    "required": [
        "passed", "overall_issues", "stations", "route_chain_valid",
        "personalization_strong", "team_roles_varied", "stories_varied",
        "preparation_concrete"
    ],
}


def _norm(value):
    value = str(value or "").lower().strip()
    value = value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", "", value)


def _enhanced_prompt(payload, feedback=""):
    base = premium.build_prompt(payload, feedback)
    final_location = str(payload.get("final_location") or "").strip()
    interests = str(payload.get("interests") or "").strip()
    return base + f"""

ZUSÄTZLICHE VERBINDLICHE RÄTSELQUALITÄT
- Die Kinder müssen aus JEDEM Rätsel selbst ableiten können, wohin es als Nächstes geht. Der nächste Ort darf niemals willkürlich nur im Elternblatt stehen.
- Stationen 1-7: Die Lösung muss eindeutig zu next_location führen. Wenn das Rätsel zunächst eine Zahl oder ein Codewort ergibt, MUSS die Kinderkarte eine sichtbare Legende/Zuordnung enthalten, die daraus den next_location ableitbar macht.
- Station 8: Die Lösung muss eindeutig zum finalen Schatzort führen: {final_location}.
- Vermeide Rätsel, bei denen die gesuchte Lösung bereits wörtlich in der Aufgabenstellung steht.
- Prüfe alle Buchstabenfolgen, Geheimcodes, Zahlenfolgen und Logikrätsel selbst auf mathematische/logische Korrektheit, bevor du antwortest.
- Ein Logikrätsel braucht genug Informationen für GENAU EINE Lösung. Keine widersprüchlichen Aussagen.
- Beobachtungs-/Suchaufgaben dürfen nur Dinge voraussetzen, die durch die Karte oder typische Gegebenheiten sicher verfügbar sind. Keine zufälligen goldenen Gegenstände oder nicht vorbereiteten Requisiten verlangen.
- puzzle_display muss der komplette spielbare Inhalt sein. Keine Formulierungen wie 'jedes Kind merkt sich ein Zeichen', wenn die konkreten Zeichen nicht auf der Karte stehen.
- hint_1 und hint_2 müssen sich konkret auf dieses Rätsel beziehen. Verboten sind generische Hinweise wie 'Achtet auf das Muster', 'Arbeitet als Team' oder 'Beginnt mit dem offensichtlichsten Teil'.
- hint_1 gibt einen kleinen Denkanstoß; hint_2 erklärt fast den Lösungsweg, ohne die Endlösung einfach zu nennen.
- Verwende mindestens 4 klar unterschiedliche team_role-Formulierungen über die acht Stationen. Nicht dieselbe Rolle wiederholen.
- Die story-Texte müssen stationsspezifisch sein und dürfen nicht achtmal dieselbe Standardsatz-Schablone verwenden.
- Mindestens 4 Stationen müssen echte persönliche Details aus diesen Interessen sinnvoll aufgreifen: {interests}.
- preparation.hide muss konkret sein, z.B. 'unter das rechte Sofakissen' oder 'mit Klebestreifen unter die Tischkante'. Vermeide achtmal 'gut sichtbar verstecken'.
- Schwierigkeit für das angegebene Alter staffeln: ungefähr 2 leichte Einstiegsaufgaben, 4 mittlere und 2 etwas kniffligere Aufgaben.
- Kein Rätsel darf nur aus 'nennt dem Spielleiter eure Lösung' bestehen. Die Karte muss selbst den Übergang zur nächsten Station ermöglichen.
- Prüfe vor Ausgabe ausdrücklich: Passt solution zum tatsächlichen Rätsel UND zu next_location?
"""


def deterministic_gate(data, payload):
    gate = premium.quality_gate(data, payload)
    errors = list(gate.get("errors") or [])
    warnings = list(gate.get("warnings") or [])
    stations = data.get("stations") or []

    # Route chain: next_location of station i must equal current_location of station i+1.
    for i in range(len(stations) - 1):
        if _norm(stations[i].get("next_location")) != _norm(stations[i + 1].get("current_location")):
            errors.append(f"Route bricht zwischen Station {i+1} und {i+2}.")

    final_location = _norm(payload.get("final_location"))
    if stations and final_location and _norm(stations[-1].get("next_location")) != final_location:
        errors.append("Station 8 führt nicht zum angegebenen Schatzort.")

    # Repeated roles/stories are a strong sign of generic generation.
    roles = [_norm(s.get("team_role")) for s in stations if s.get("team_role")]
    if len(set(roles)) < 4:
        errors.append("Teamrollen sind zu wenig abwechslungsreich (<4 unterschiedliche Rollen).")

    stories = [_norm(s.get("story")) for s in stations if s.get("story")]
    if len(set(stories)) < 6:
        errors.append("Stationsgeschichten sind zu repetitiv.")

    generic_hints = [
        "achtetaufdasmuster", "arbeitetalsteam", "beginntmitdemoffensichtlichstenteil",
        "schautgenauhin", "denktgemeinsamnach"
    ]
    for idx, station in enumerate(stations, 1):
        h1 = _norm(station.get("hint_1")); h2 = _norm(station.get("hint_2"))
        if h1 == h2:
            errors.append(f"Station {idx}: Tipp 1 und Tipp 2 sind identisch.")
        if any(g in h1 or g in h2 for g in generic_hints):
            errors.append(f"Station {idx}: Hinweise sind zu generisch.")
        if _norm(station.get("current_location")) == _norm(station.get("next_location")) and idx < 8:
            errors.append(f"Station {idx}: aktueller und nächster Ort sind identisch.")

    hides = [_norm(x.get("hide")) for x in (data.get("preparation") or [])]
    if len(set(hides)) < 5:
        errors.append("Versteckanweisungen sind zu repetitiv/generisch.")

    gate["errors"] = errors
    gate["warnings"] = warnings
    gate["passed"] = not errors
    return gate


def semantic_critic(client, model, data, payload):
    critic_input = {
        "child_age": payload.get("age"),
        "interests": payload.get("interests"),
        "theme": payload.get("theme"),
        "final_location": payload.get("final_location"),
        "quest": data,
    }
    response = client.responses.create(
        model=model,
        reasoning={"effort": "high"},
        max_output_tokens=6000,
        input=(
            "Du bist ein strenger Redakteur und Rätseldesigner für Premium-Kindergeburtstage. "
            "Prüfe die folgende Quest, indem du jedes der 8 Rätsel tatsächlich selbst löst. "
            "Akzeptiere eine Station nur, wenn der Rätselinhalt auf der Kinderkarte vollständig, logisch korrekt, "
            "altersgerecht und eindeutig lösbar ist und die Lösung aus Sicht der Kinder nachvollziehbar zum angegebenen "
            "next_location führt. Eine nur im Elternblatt behauptete Lösung zählt NICHT. Prüfe außerdem, ob die Antwort "
            "nicht bereits verraten wird, beide Hinweise konkret und abgestuft helfen, Teamrollen und Geschichten variieren, "
            "die Versteckanweisungen konkret sind und die Interessen echte Personalisierung erzeugen. "
            "Setze passed nur auf true, wenn keine relevante Schwäche besteht.\n\n"
            + json.dumps(critic_input, ensure_ascii=False)
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": "geburtstagsquest_critic",
                "description": "Strenge semantische Qualitätsprüfung einer KindergeburtstagsQuest.",
                "schema": CRITIC_SCHEMA,
                "strict": True,
            },
            "verbosity": "medium",
        },
    )
    return json.loads(response.output_text)


def _feedback_from_checks(rule_gate, critic):
    lines = []
    for issue in (rule_gate.get("errors") or []):
        lines.append(f"Regelprüfung: {issue}")
    for issue in (critic.get("overall_issues") or []):
        lines.append(f"Semantik: {issue}")
    for station in critic.get("stations") or []:
        if not all([
            station.get("solvable"), station.get("logically_correct"),
            station.get("route_is_derivable"), station.get("answer_not_leaked"),
            station.get("hints_are_useful"), station.get("age_appropriate"),
            station.get("self_contained")
        ]):
            lines.append(f"Station {station.get('number')}: {station.get('issue')}")
    if not critic.get("route_chain_valid"): lines.append("Route ist semantisch nicht durchgängig.")
    if not critic.get("personalization_strong"): lines.append("Personalisierung ist zu oberflächlich.")
    if not critic.get("team_roles_varied"): lines.append("Teamrollen stärker variieren.")
    if not critic.get("stories_varied"): lines.append("Stationsgeschichten stärker variieren.")
    if not critic.get("preparation_concrete"): lines.append("Versteckanweisungen konkreter machen.")
    return "\n".join(f"- {line}" for line in lines[:30])


def generate_quest(payload):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=300.0)
    model = os.getenv("OPENAI_MODEL", "gpt-6-luna")
    feedback = ""
    last_feedback = ""

    for _ in range(3):
        response = client.responses.create(
            model=model,
            input=_enhanced_prompt(payload, feedback),
            reasoning={"effort": "high"},
            max_output_tokens=14000,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "geburtstagsquest_premium_v2",
                    "description": "Premium, druckfertiges und logisch geprüftes Party-Kit mit acht Stationen.",
                    "schema": premium.QUEST_SCHEMA,
                    "strict": True,
                },
                "verbosity": "medium",
            },
        )
        data = json.loads(response.output_text)
        rule_gate = deterministic_gate(data, payload)
        critic = semantic_critic(client, model, data, payload)

        if rule_gate["passed"] and critic.get("passed"):
            data["quality_gate"] = {
                **rule_gate,
                "semantic_critic": {
                    "passed": True,
                    "route_chain_valid": critic.get("route_chain_valid"),
                    "personalization_strong": critic.get("personalization_strong"),
                    "team_roles_varied": critic.get("team_roles_varied"),
                    "stories_varied": critic.get("stories_varied"),
                    "preparation_concrete": critic.get("preparation_concrete"),
                },
            }
            return json.dumps(data, ensure_ascii=False)

        last_feedback = _feedback_from_checks(rule_gate, critic)
        feedback = last_feedback

    raise RuntimeError("Premium semantic QA failed after 3 attempts: " + last_feedback[:2500])


def install(legacy):
    legacy.generate_quest = generate_quest
    legacy.app.logger.warning("GeburtstagsQuest semantic puzzle QA v2 enabled")
