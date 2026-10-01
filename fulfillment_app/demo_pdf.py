import io

from flask import abort, send_file


def _demo_payload(theme):
    names = {
        "detective": ("Detektivmission", "Emma", "Geheimcodes, Detektivgeschichten, Rätsel"),
        "dino": ("Dinosaurierexpedition", "Emma", "Dinosaurier, Fossilien, Abenteuer"),
        "space": ("Weltraummission", "Emma", "Weltraum, Planeten, Raketen"),
        "magic": ("Zauberschule", "Emma", "Magie, Rätsel, fantastische Geschichten"),
        "animal": ("Tierretter", "Emma", "Tiere, Natur, Tierrettung"),
        "research": ("Forscher-Geheimmission", "Emma", "Experimente, Natur, Entdeckungen"),
    }
    selected = names.get(theme)
    if not selected:
        return None
    label, child, interests = selected
    return {
        "child_name": child,
        "age": 9,
        "group_size": 7,
        "theme": label,
        "interests": interests,
        "play_area": "drinnen und draußen",
        "locations": ["Küche", "Flur", "Garten", "Terrasse", "Bücherregal", "Sofa", "Esstisch", "Gartenhaus"],
        "final_location": "Gartenhaus",
    }


def _demo_quest(payload):
    theme = payload["theme"]
    child = payload["child_name"]
    theme_title = {
        "Detektivmission": "Der Fall der verschwundenen Schatzkarte",
        "Dinosaurierexpedition": "Das Geheimnis der verlorenen Dino-Spur",
        "Weltraummission": "Mission Sternenkompass",
        "Zauberschule": "Das Rätsel des verschwundenen Zauberbuchs",
        "Tierretter": "Die Mission der geheimen Tierspuren",
        "Forscher-Geheimmission": "Die Expedition zum verborgenen Forscherschatz",
    }[theme]
    places = ["Küche", "Flur", "Garten", "Terrasse", "Bücherregal", "Sofa", "Esstisch", "Gartenhaus"]
    puzzle_types = ["code", "logic", "observation", "movement", "word", "teamwork", "number", "search"]
    stations = []
    for i, place in enumerate(places):
        nxt = places[i + 1] if i < 7 else "Gartenhaus"
        displays = [
            "K = 11 · U = 21 · E = 5 · C = 3 · H = 8 · E = 5\n11 - 21 - 5 - 3 - 8 - 5",
            "Drei Spuren: ROT, BLAU, GRÜN.\nROT ist nicht richtig. BLAU liegt neben ROT. Welche Spur bleibt?",
            "Findet auf der Karte: 3 Blätter · 2 Sterne · 1 Kompass. Die markierten Anfangsbuchstaben ergeben den nächsten Ort.",
            "Team-Challenge: Bildet eine Kette, ohne euch loszulassen. Die Person am Ende liest danach den verdeckten Hinweis vor.",
            "B U E C H E R R E G A L\nStreicht jeden zweiten Buchstaben und lest die verbleibende Botschaft.",
            "Jede Person erhält ein Symbol. Nur wenn ihr alle Symbole in der richtigen Reihenfolge zusammenlegt, erscheint das Lösungswort.",
            "2 · 4 · 8 · 16 · ?\nNehmt die fehlende Zahl und sucht das Feld mit derselben Zahl auf der Karte.",
            "Sucht gemeinsam 4 markierte Spuren. Ordnet sie von klein nach groß. Die Rückseiten ergeben den Finalhinweis.",
        ]
        stations.append({
            "number": i + 1,
            "title": ["Die geheime Botschaft", "Die drei Spuren", "Der versteckte Blick", "Die Team-Challenge", "Der Buchstabencode", "Das Symbol-Team", "Der Zahlencode", "Der Finalhinweis"][i],
            "current_location": place,
            "next_location": nxt,
            "story": f"{child}, eure Mission geht weiter. An dieser Station wartet eine neue Spur, die nur euer Team gemeinsam entschlüsseln kann.",
            "child_card": "Löst die Aufgabe auf dieser Karte gemeinsam.",
            "puzzle_type": puzzle_types[i],
            "puzzle_display": displays[i],
            "task": displays[i],
            "solution": f"Die Lösung führt zum nächsten Ort: {nxt}.",
            "hint_1": "Schaut euch zuerst genau an, was auf der Karte anders oder besonders markiert ist.",
            "hint_2": f"Die gesuchte Lösung ist ein Ort. Denkt an {nxt}.",
            "team_role": ["Codechef", "Spurensucher", "Beobachter", "Teamsprecher", "Wortdetektiv", "Symbolwächter", "Zahlenprofi", "Kartenleser"][i],
            "duration_minutes": 5,
        })
    return {
        "title": f"{child}s {theme_title}",
        "subtitle": "Eine ganz persönliche GeburtstagsQuest",
        "parent_summary": "Ein druckfertiges Abenteuer mit acht Stationen für sieben Kinder.",
        "setup_minutes": 15,
        "party_schedule": ["+00:00 Ankommen", "+00:20 Kuchen & Geschenke", "+00:45 Quest starten", "+01:35 Schatz finden", "+01:45 Urkunde & Bonusmission"],
        "materials": ["Ausgedruckte Kinderkarten", "Schere", "Klebeband", "Stifte", "Schatz oder Mitgebsel"],
        "preparation": [{"station": i + 1, "location": places[i], "hide": f"Kinderkarte {i+1} gut sichtbar, aber nicht sofort auffällig bei {places[i]} platzieren.", "item": "Kinderkarte"} for i in range(8)],
        "intro_story": f"Heute wartet auf {child} und das Team eine ganz besondere Mission. Acht Spuren wurden an geheimen Orten hinterlassen. Nur wenn ihr zusammenarbeitet, könnt ihr den Weg bis zum Schatz entschlüsseln.",
        "stations": stations,
        "finale": f"Geschafft! {child} und das Team haben alle acht Spuren gelöst. Der Schatz wartet im Gartenhaus. Jetzt dürft ihr eure Mission feiern!",
        "certificate_text": f"hat gemeinsam mit dem Team acht knifflige Stationen gemeistert und die große {theme}-Mission erfolgreich abgeschlossen.",
        "bonus_game": "Bonus-Mission: Erfindet gemeinsam einen Teamruf und löst danach eine 10-Minuten-Bewegungs-Challenge.",
        "indoor_plan": "Bei Regen können Garten und Terrasse übersprungen werden. Die jeweilige Kinderkarte wird direkt im Flur oder Wohnzimmer übergeben.",
        "route_check": ["Route geprüft", "Finalort geprüft"],
    }


def install(legacy):
    @legacy.app.get("/muster/<theme>.pdf")
    def sample_pdf(theme):
        payload = _demo_payload(theme)
        if payload is None:
            abort(404)
        quest = _demo_quest(payload)
        pdf_bytes = legacy.structured_pdf_bytes(payload, quest)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=False,
            download_name=f"GeburtstagsQuest-Muster-{theme}.pdf",
        )
