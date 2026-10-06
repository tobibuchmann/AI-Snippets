import re

from . import premium
from . import quality_v2


def _norm(value):
    value = str(value or "").lower().strip()
    value = value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", "", value)


def install():
    original_build_prompt = premium.build_prompt
    original_gate = quality_v2.deterministic_gate

    def build_prompt(payload, feedback=""):
        base = original_build_prompt(payload, feedback)
        return base + """

ROBUSTE ROUTENMECHANIK — VERBINDLICH
- Das eigentliche Ergebnis JEDER Station ist der nächste Ort. solution muss den next_location wörtlich enthalten, am besten exakt als "Zielort: <next_location>".
- Die Kinder müssen den next_location ausschließlich aus child_card + puzzle_display ableiten können. Das Elternblatt darf keine zusätzliche Information enthalten, die für die Ortslösung nötig ist.
- Bevorzuge einfache, robuste Ortsrätsel: Buchstaben ergeben direkt den exakten Ortsnamen, eine eindeutige Bild-/Symbolzuordnung ergibt direkt den Ortsnamen oder eine sichtbare Legende ordnet EIN Ergebnis EINEM Zielort zu.
- Wenn ein Rätsel zunächst einen Code, eine Zahl oder ein Lösungswort erzeugt, MUSS puzzle_display auf derselben Karte eine vollständige Legende enthalten, die dieses Ergebnis eindeutig zum exakten next_location übersetzt.
- Keine abgeschnittenen Ortsnamen wie GART statt GARTEN. Keine fehleranfälligen Rückwärtswörter, mehrstufigen Caesar-Codes oder komplizierten Substitutionen, wenn eine einfachere Mechanik möglich ist.
- Bei Bewegungs-, Such- und Teamaufgaben folgt am Ende immer ein kurzer, vollständig auf der Karte enthaltener Zielort-Hinweis.
- Prüfe buchstabengetreu: Das Ergebnis des Rätsels muss exakt zum geschriebenen next_location passen.
- Erfinde keine Ortsoption, die nicht in den erlaubten Orten steht.
- Die Abwechslung entsteht durch die AUFGABE (Suchen, Beobachten, Bewegen, Logik, Teamwork), nicht durch unnötig komplizierte Verschlüsselung des nächsten Orts.
"""

    def deterministic_gate(data, payload):
        gate = original_gate(data, payload)
        errors = list(gate.get("errors") or [])
        for index, station in enumerate(data.get("stations") or [], 1):
            target = _norm(station.get("next_location"))
            solution = _norm(station.get("solution"))
            if target and target not in solution:
                errors.append(
                    f"Station {index}: solution nennt den next_location nicht ausdrücklich; "
                    "Routenlösung muss den Zielort wörtlich enthalten."
                )
        gate["errors"] = errors
        gate["passed"] = not errors
        return gate

    premium.build_prompt = build_prompt
    quality_v2.deterministic_gate = deterministic_gate
