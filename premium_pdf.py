import html
import io
import math

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

CREAM = colors.HexColor("#FBF8F1")
INK = colors.HexColor("#241C33")
MUTED = colors.HexColor("#746D7C")
PURPLE = colors.HexColor("#6E43B9")
PURPLE_DARK = colors.HexColor("#21152F")
GOLD = colors.HexColor("#C7A24A")
LAVENDER = colors.HexColor("#EFE8FB")
WHITE = colors.white
LINE = colors.HexColor("#E8E1D7")
PALE_BLUE = colors.HexColor("#EAF4F8")
PALE_GREEN = colors.HexColor("#E8F5EC")
PALE_YELLOW = colors.HexColor("#FFF5D6")
PALE_RED = colors.HexColor("#FBE8E8")


def safe(value):
    return html.escape(str(value or "")).replace("\n", "<br/>")


def theme_label(theme):
    value = (theme or "").lower()
    if "detektiv" in value: return "FALLAKTE - GEHEIM"
    if "weltraum" in value: return "MISSION - KOSMOS"
    if "dino" in value: return "EXPEDITION - URZEIT"
    if "zauber" in value: return "MAGISCHE MISSION"
    if "tier" in value: return "RETTUNGSMISSION"
    return "GEHEIMMISSION"


def _wrap(canvas, value, font, size, width):
    lines, current = [], ""
    for word in str(value or "").split():
        test = (current + " " + word).strip()
        if current and canvas.stringWidth(test, font, size) > width:
            lines.append(current); current = word
        else:
            current = test
    if current: lines.append(current)
    return lines


def _star(canvas, cx, cy, r):
    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        radius = r if i % 2 == 0 else r * 0.42
        points.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
    path = canvas.beginPath(); path.moveTo(*points[0])
    for point in points[1:]: path.lineTo(*point)
    path.close(); canvas.drawPath(path, stroke=0, fill=1)


class CoverPanel(Flowable):
    def __init__(self, title, subtitle, child_name, theme, setup_minutes):
        super().__init__(); self.width = 174 * mm; self.height = 222 * mm
        self.title = title; self.subtitle = subtitle; self.child_name = child_name
        self.theme = theme; self.setup_minutes = setup_minutes

    def draw(self):
        c, w, h = self.canv, self.width, self.height
        c.setFillColor(PURPLE_DARK); c.roundRect(0, 0, w, h, 8 * mm, stroke=0, fill=1)
        c.setFillColor(colors.HexColor("#493658"))
        for x, y, r in [(17,198,2.2),(145,190,1.5),(151,36,2),(27,43,1.3),(134,132,1.2),(39,151,1.1)]:
            c.circle(x*mm, y*mm, r*mm, stroke=0, fill=1)
        cx, cy = w/2, h-45*mm
        c.setStrokeColor(GOLD); c.setLineWidth(2.4); c.circle(cx-4*mm, cy+3*mm, 12*mm, stroke=1, fill=0); c.line(cx+5*mm, cy-6*mm, cx+18*mm, cy-19*mm)
        c.setFillColor(GOLD); c.setFont("Helvetica-Bold", 8); c.drawCentredString(w/2, h-78*mm, "GEBURTSTAGSQUEST")
        c.setFillColor(colors.HexColor("#D8C38E")); c.drawCentredString(w/2, h-89*mm, theme_label(self.theme))
        c.setStrokeColor(GOLD); c.line(w/2-22*mm, h-96*mm, w/2+22*mm, h-96*mm)
        c.setFillColor(WHITE); c.setFont("Helvetica-Bold", 20)
        y = h - 119*mm
        for line in _wrap(c, self.title or "Deine GeburtstagsQuest", "Helvetica-Bold", 20, w-28*mm)[:3]:
            c.drawCentredString(w/2, y, line); y -= 9*mm
        c.setFillColor(colors.HexColor("#C9BFD2")); c.setFont("Helvetica", 10)
        for i, line in enumerate(_wrap(c, self.subtitle or "Ein persönliches Abenteuer für euren Kindergeburtstag", "Helvetica", 10, w-36*mm)[:3]):
            c.drawCentredString(w/2, y-3*mm-i*5*mm, line)
        c.setStrokeColor(colors.HexColor("#6D5B78")); c.roundRect(23*mm, 24*mm, w-46*mm, 19*mm, 9.5*mm, stroke=1, fill=0)
        c.setFillColor(WHITE); c.setFont("Helvetica-Bold", 9); c.drawCentredString(w/2, 35.5*mm, f"Für {self.child_name}  |  Aufbau ca. {self.setup_minutes} Min.")
        c.setFillColor(colors.HexColor("#C9BFD2")); c.setFont("Helvetica", 8); c.drawCentredString(w/2, 29.7*mm, "Ausdrucken - verstecken - losspielen")


class SectionGraphic(Flowable):
    def __init__(self, kind="steps", height=34*mm):
        super().__init__(); self.width = 168*mm; self.height = height; self.kind = kind

    def draw(self):
        c, w, h = self.canv, self.width, self.height
        c.setFillColor(LAVENDER); c.roundRect(0, 0, w, h, 5*mm, stroke=0, fill=1)
        c.setStrokeColor(PURPLE); c.setLineWidth(1.5)
        if self.kind == "steps":
            xs = [28*mm, 84*mm, 140*mm]
            for x, (number, label) in zip(xs, [("1","DRUCKEN"),("2","VERSTECKEN"),("3","STARTEN")]):
                c.setFillColor(PURPLE); c.circle(x, h*0.58, 8*mm, stroke=0, fill=1)
                c.setFillColor(WHITE); c.setFont("Helvetica-Bold", 12); c.drawCentredString(x, h*0.58-1.5*mm, number)
                c.setFillColor(INK); c.setFont("Helvetica-Bold", 8); c.drawCentredString(x, 5*mm, label)
            c.setStrokeColor(colors.HexColor("#CFC2E5")); c.line(xs[0]+9*mm,h*0.58,xs[1]-9*mm,h*0.58); c.line(xs[1]+9*mm,h*0.58,xs[2]-9*mm,h*0.58)
        elif self.kind == "print":
            c.roundRect(20*mm,8*mm,32*mm,17*mm,2*mm,stroke=1,fill=0); c.rect(26*mm,18*mm,20*mm,12*mm,stroke=1,fill=0)
            c.rect(72*mm,8*mm,20*mm,20*mm,stroke=1,fill=0)
            c.circle(124*mm,17*mm,4*mm,stroke=1,fill=0); c.circle(136*mm,17*mm,4*mm,stroke=1,fill=0); c.line(128*mm,20*mm,144*mm,29*mm); c.line(132*mm,14*mm,144*mm,7*mm)
            c.setFillColor(INK); c.setFont("Helvetica-Bold",8); c.drawCentredString(36*mm,3*mm,"DRUCKEN"); c.drawCentredString(82*mm,3*mm,"KINDERKARTEN"); c.drawCentredString(134*mm,3*mm,"AUSSCHNEIDEN")
        else:
            c.circle(30*mm,17*mm,8*mm,stroke=1,fill=0); c.line(38*mm,11*mm,48*mm,4*mm)
            c.roundRect(72*mm,8*mm,24*mm,18*mm,2*mm,stroke=1,fill=0); c.line(77*mm,20*mm,91*mm,20*mm); c.line(77*mm,15*mm,91*mm,15*mm)
            c.circle(135*mm,17*mm,9*mm,stroke=1,fill=0); c.setFillColor(PURPLE); c.circle(135*mm,17*mm,2*mm,stroke=0,fill=1)


class CertificateArtwork(Flowable):
    def __init__(self, child_name, theme, text):
        super().__init__(); self.width = 174*mm; self.height = 220*mm
        self.child_name = child_name; self.theme = theme; self.text = text

    def draw(self):
        c, w, h = self.canv, self.width, self.height
        c.setFillColor(CREAM); c.roundRect(0,0,w,h,5*mm,stroke=0,fill=1)
        c.setStrokeColor(PURPLE_DARK); c.setLineWidth(2); c.roundRect(5*mm,5*mm,w-10*mm,h-10*mm,4*mm,stroke=1,fill=0)
        c.setStrokeColor(GOLD); c.setLineWidth(1); c.roundRect(9*mm,9*mm,w-18*mm,h-18*mm,3*mm,stroke=1,fill=0)
        c.setFillColor(GOLD)
        for x,y in [(16,16),(158,16),(16,204),(158,204)]: _star(c,x*mm,y*mm,4*mm)
        c.setFillColor(PURPLE_DARK); c.circle(w/2,h-46*mm,18*mm,stroke=0,fill=1); c.setStrokeColor(GOLD); c.setLineWidth(2); c.circle(w/2,h-46*mm,14*mm,stroke=1,fill=0); c.setFillColor(GOLD); _star(c,w/2,h-46*mm,6*mm)
        c.setFillColor(PURPLE); c.setFont("Helvetica-Bold",9); c.drawCentredString(w/2,h-76*mm,"GEBURTSTAGSQUEST")
        c.setFillColor(INK); c.setFont("Helvetica-Bold",28); c.drawCentredString(w/2,h-93*mm,"URKUNDE")
        c.setFillColor(MUTED); c.setFont("Helvetica",10); c.drawCentredString(w/2,h-105*mm,"Diese Auszeichnung geht an")
        c.setFillColor(PURPLE_DARK); c.setFont("Helvetica-Bold",24); c.drawCentredString(w/2,h-123*mm,str(self.child_name or "Geburtstagsheld"))
        c.setStrokeColor(GOLD); c.line(35*mm,h-130*mm,w-35*mm,h-130*mm)
        c.setFillColor(INK); c.setFont("Helvetica",11); y=h-146*mm
        for line in _wrap(c,self.text,"Helvetica",11,w-42*mm)[:5]: c.drawCentredString(w/2,y,line); y-=6*mm
        c.setFillColor(PURPLE); c.setFont("Helvetica-Bold",10); c.drawCentredString(w/2,38*mm,"MISSION GESCHAFFT - TEAMWORK BEWIESEN - SCHATZ GEFUNDEN")
        c.setStrokeColor(LINE); c.line(30*mm,24*mm,75*mm,24*mm); c.line(w-75*mm,24*mm,w-30*mm,24*mm)
        c.setFillColor(MUTED); c.setFont("Helvetica",8); c.drawCentredString(52.5*mm,18*mm,"Datum"); c.drawCentredString(w-52.5*mm,18*mm,"Unterschrift")
        c.setFillColor(GOLD); c.setFont("Helvetica-Bold",8); c.drawCentredString(w/2,18*mm,theme_label(self.theme))


def footer(canvas, doc):
    canvas.saveState(); width,_ = A4
    canvas.setStrokeColor(LINE); canvas.line(18*mm,13*mm,width-18*mm,13*mm)
    canvas.setFillColor(MUTED); canvas.setFont("Helvetica",8); canvas.drawString(18*mm,8*mm,"GeburtstagsQuest - Dein persönliches Party-Kit"); canvas.drawRightString(width-18*mm,8*mm,f"Seite {doc.page}"); canvas.restoreState()


def styles():
    b = getSampleStyleSheet()
    return {
        "eyebrow": ParagraphStyle("eyebrow",parent=b["BodyText"],fontName="Helvetica-Bold",fontSize=8,leading=10,textColor=GOLD,spaceAfter=5),
        "h1": ParagraphStyle("h1",parent=b["Heading1"],fontName="Helvetica-Bold",fontSize=20,leading=24,textColor=PURPLE_DARK,spaceAfter=9),
        "h2": ParagraphStyle("h2",parent=b["Heading2"],fontName="Helvetica-Bold",fontSize=14,leading=18,textColor=PURPLE,spaceBefore=6,spaceAfter=5),
        "body": ParagraphStyle("body",parent=b["BodyText"],fontSize=10.5,leading=15,textColor=INK,spaceAfter=6),
        "small": ParagraphStyle("small",parent=b["BodyText"],fontSize=8.7,leading=12,textColor=MUTED,spaceAfter=3),
        "child": ParagraphStyle("child",parent=b["BodyText"],fontName="Helvetica-Bold",fontSize=12.2,leading=17,textColor=PURPLE_DARK,spaceAfter=4),
        "puzzle": ParagraphStyle("puzzle",parent=b["BodyText"],fontName="Courier-Bold",fontSize=11.7,leading=17,textColor=INK,alignment=TA_CENTER,spaceAfter=2),
        "sub": ParagraphStyle("sub",parent=b["BodyText"],fontSize=12,leading=17,textColor=MUTED,spaceAfter=12),
        "center": ParagraphStyle("center",parent=b["BodyText"],fontSize=10.5,leading=15,textColor=INK,alignment=TA_CENTER,spaceAfter=5),
    }


def badge(text, st, bg=PURPLE_DARK, fg=WHITE):
    p = Paragraph(safe(text), ParagraphStyle("badge",parent=st["small"],fontName="Helvetica-Bold",fontSize=7.5,leading=9,textColor=fg,alignment=TA_CENTER))
    t = Table([[p]],colWidths=[47*mm]); t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),bg),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)])); return t


def box(label, content, st, bg=LAVENDER, style="body", border=PURPLE):
    t = Table([[Paragraph(f"<b>{safe(label)}</b><br/>{safe(content)}",st[style])]],colWidths=[168*mm])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),bg),("BOX",(0,0),(-1,-1),0.8,border),("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),("TOPPADDING",(0,0),(-1,-1),9),("BOTTOMPADDING",(0,0),(-1,-1),9)])); return t


def info(title, text, st, number=None):
    left = Paragraph(f"<b>{safe(number or '')}</b>",ParagraphStyle("num",parent=st["body"],fontName="Helvetica-Bold",fontSize=16,textColor=PURPLE,alignment=TA_CENTER))
    right = Paragraph(f"<b>{safe(title)}</b><br/>{safe(text)}",st["body"])
    t=Table([[left,right]],colWidths=[18*mm,150*mm]); t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),WHITE),("BOX",(0,0),(-1,-1),0.7,LINE),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("PADDING",(0,0),(-1,-1),8)])); return t


def parent_header(title, st):
    return [badge("NUR FÜR ELTERN",st),Spacer(1,3*mm),Paragraph(title,st["h1"])]


def structured_pdf_bytes(q, payload):
    buf=io.BytesIO(); doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=18*mm,bottomMargin=18*mm,title=str(q.get("title") or "GeburtstagsQuest"),author="GeburtstagsQuest"); st=styles(); story=[]
    story += [CoverPanel(q.get("title"),q.get("subtitle"),payload.get("child_name"),payload.get("theme"),q.get("setup_minutes")),PageBreak()]

    story += parent_header("So funktioniert eure GeburtstagsQuest",st)
    story += [Paragraph("Du musst kein Spiel vorbereiten oder Rätsel erfinden. Route, Aufgaben, Hinweise und Lösungen sind bereits auf euer Kind und eure Orte abgestimmt.",st["sub"]),SectionGraphic("steps"),Spacer(1,5*mm),info("Drucken","Drucke dieses PDF in A4. Kinderkarten bitte einseitig drucken; Elternseiten bleiben bei dir.",st,"1"),Spacer(1,3*mm),info("Verstecken","Lege jede Kinderkarte an den Ort aus dem Vorbereitungsplan. Den Schatz legst du an den Finalort.",st,"2"),Spacer(1,3*mm),info("Starten","Lies die Einstiegsgeschichte vor. Danach spielen die Kinder möglichst selbstständig.",st,"3"),Spacer(1,5*mm),box("Dein Zeitaufwand",f"Geplant sind ca. {safe(q.get('setup_minutes'))} Minuten Aufbau und 45-60 Minuten Spielzeit.",st,PALE_GREEN,border=colors.HexColor("#9AC6A3")),PageBreak()]

    story += parent_header("Was muss ich drucken und ausschneiden?",st)
    story += [SectionGraphic("print"),Spacer(1,5*mm),info("Elternseiten","Schnellstart, Zeitplan, Material, Vorbereitung, Lösungen, Hinweise und Routencheck. Diese Seiten bleiben bei dir.",st),Spacer(1,3*mm),info("Kinderkarten","Jede Station hat eine eigene Karte. Sie kann ausgeschnitten oder als ganze Seite versteckt werden.",st),Spacer(1,3*mm),info("Urkunde","Die letzte Seite ist für das Finale gedacht. Auf 120-160 g/m2 Papier wirkt sie besonders hochwertig.",st),Spacer(1,5*mm),box("Druck-Tipp","Normales A4-Papier reicht. Farbe ist schön, aber nicht zwingend.",st,LAVENDER),PageBreak()]

    story += parent_header("Dein Job während des Spiels",st)
    for title,text in [("Start","Nur die Einstiegsgeschichte vorlesen und dann Station 1 starten lassen."),("Erst beobachten","Gib der Gruppe Zeit zum Diskutieren. Nicht sofort eingreifen, wenn es kurz stockt."),("Hinweise dosieren","Wenn die Gruppe wirklich festhängt: zuerst Tipp 1. Tipp 2 erst danach."),("Alle beteiligen","Nutze die Teamrollen. Wechselnde Aufgaben verhindern, dass immer dasselbe Kind alles löst."),("Tempo steuern","Zu schnell? Bonusspiel nutzen. Zu langsam? Tipp 2 früher geben oder eine Station überspringen.")]:
        story += [info(title,text,st),Spacer(1,3*mm)]
    story += [PageBreak()]

    story += parent_header("So kann euer Geburtstag ablaufen",st)
    story += [Paragraph(safe(q.get("parent_summary")),st["body"]),Paragraph("Vorschlag für euren Zeitplan",st["h2"])]
    for entry in q.get("party_schedule") or []: story.append(Paragraph("- "+safe(entry),st["body"]))
    story += [Paragraph("Material",st["h2"])]
    for item in q.get("materials") or []: story.append(Paragraph("[ ] "+safe(item),st["body"]))
    story += [Spacer(1,3*mm),box("Schatz-Ideen - optional","Kleine Mitgebsel, Sticker, Mini-Notizblöcke, Detektiv-Ausweise, Edelsteine aus Acryl oder ein gemeinsamer Hauptpreis. Lebensmittel sind nicht notwendig.",st,PALE_YELLOW,border=GOLD),PageBreak()]

    story += parent_header("Vorbereitung und Versteckplan",st)
    story += [Paragraph("Gehe die Liste einmal von oben nach unten durch. Wenn alle acht Karten liegen, ist die Quest startklar.",st["sub"])]
    rows=[[Paragraph("<b>Nr.</b>",st["small"]),Paragraph("<b>Hier verstecken</b>",st["small"]),Paragraph("<b>Was tun?</b>",st["small"]),Paragraph("<b>Material</b>",st["small"])]]
    for r in q.get("preparation") or []: rows.append([Paragraph(str(r.get("station","")),st["small"]),Paragraph(safe(r.get("location")),st["small"]),Paragraph(safe(r.get("hide")),st["small"]),Paragraph(safe(r.get("item")),st["small"])])
    prep=Table(rows,colWidths=[14*mm,40*mm,73*mm,41*mm],repeatRows=1); prep.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),PURPLE_DARK),("TEXTCOLOR",(0,0),(-1,0),WHITE),("GRID",(0,0),(-1,-1),0.35,LINE),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),5)]))
    story += [prep,Spacer(1,5*mm),box("Wichtig","Lösungen und Elternblätter nicht mit verstecken. Kinder brauchen nur die Kinderkarten.",st,PALE_RED,border=colors.HexColor("#D9A0A0")),PageBreak()]

    story += parent_header("Plan B und Hilfe, falls etwas hakt",st)
    story += [Paragraph("Schlechtwetter-Plan B",st["h2"])]
    for item in q.get("indoor_fallback") or []: story.append(Paragraph("- "+safe(item),st["body"]))
    story += [Spacer(1,2*mm),Paragraph("Wenn etwas nicht nach Plan läuft",st["h2"])]
    for title,text in [("Die Kinder sind zu schnell","Nutze das Bonusspiel oder lass die Gruppe eine gelöste Station noch einmal erklären."),("Die Kinder hängen fest","Tipp 1 geben, kurz warten, dann Tipp 2. Die Lösung erst danach verraten."),("Ein Versteck passt doch nicht","Lege die Karte an einen anderen erlaubten Ort und nenne den Ort kurz mündlich."),("Ein Kind liest unsicher","Lasst die Karte gemeinsam laut lesen. Die Teamrolle kann an ein anderes Kind wechseln."),("Ihr seid in Zeitnot","Eine Station darf übersprungen werden. Nutze die Lösungsübersicht, um direkt zum nächsten Ort zu wechseln.")]:
        story += [info(title,text,st),Spacer(1,2*mm)]
    story += [PageBreak()]

    story += [badge("JETZT GEHT ES LOS",st,bg=GOLD,fg=PURPLE_DARK),Spacer(1,4*mm),Paragraph("Start der Mission",st["h1"]),box("Zum Vorlesen",q.get("intro_story"),st,CREAM,border=GOLD),Spacer(1,6*mm),Paragraph("Danach bekommt die Gruppe Kinderkarte 1 oder sucht sie am ersten vorbereiteten Ort.",st["center"]),PageBreak()]

    for s in q.get("stations") or []:
        n=s.get("number")
        story += [badge("FÜR DIE KINDER - AUSSCHNEIDEN",st,bg=PURPLE),Spacer(1,3*mm),Paragraph(f"KINDERKARTE {n}: {safe(s.get('title'))}",st["h1"]),Paragraph(theme_label(payload.get("theme")),st["eyebrow"]),Table([[Paragraph(f"<b>Gefunden bei</b><br/>{safe(s.get('current_location'))}",st["small"]),Paragraph(f"<b>Rätseltyp</b><br/>{safe(s.get('puzzle_type'))}",st["small"]),Paragraph(f"<b>Zeit</b><br/>{safe(s.get('duration_minutes'))} Min.",st["small"]) ]],colWidths=[72*mm,54*mm,42*mm],style=TableStyle([("BACKGROUND",(0,0),(-1,-1),CREAM),("BOX",(0,0),(-1,-1),0.6,GOLD),("PADDING",(0,0),(-1,-1),6)])),Spacer(1,5*mm),SectionGraphic("quest",height=28*mm),Spacer(1,4*mm),box("MISSION",s.get("child_card"),st,LAVENDER,"child"),Spacer(1,4*mm),box("RÄTSEL",s.get("puzzle_display"),st,PALE_BLUE,"puzzle",border=colors.HexColor("#95BBCB")),Spacer(1,4*mm),box("TEAMROLLE",s.get("team_role"),st,PALE_GREEN,border=colors.HexColor("#9AC6A3")),Spacer(1,5*mm),Paragraph("Falls ihr feststeckt: bittet zuerst um Tipp 1. Tipp 2 ist die stärkere Hilfe.",st["small"]),PageBreak()]

        story += parent_header(f"Station {n}: {safe(s.get('title'))}",st)
        story += [Table([[Paragraph(f"<b>Aktueller Ort</b><br/>{safe(s.get('current_location'))}",st["small"]),Paragraph(f"<b>Danach weiter zu</b><br/>{safe(s.get('next_location'))}",st["small"]) ]],colWidths=[84*mm,84*mm],style=TableStyle([("BACKGROUND",(0,0),(-1,-1),CREAM),("BOX",(0,0),(-1,-1),0.6,GOLD),("PADDING",(0,0),(-1,-1),7)])),Spacer(1,4*mm),box("DEIN JOB AN DIESER STATION","Kinderkarte vorher am angegebenen Ort verstecken. Die Gruppe selbst lösen lassen. Nur wenn nötig Tipp 1 geben, danach Tipp 2.",st,PALE_YELLOW,border=GOLD),Spacer(1,4*mm),Paragraph(safe(s.get("story")),st["body"]),box("Aufgabe / Erwartung",s.get("task"),st,CREAM,border=LINE),Spacer(1,3*mm),box("Lösung",s.get("solution"),st,PALE_GREEN,border=colors.HexColor("#9AC6A3")),Spacer(1,3*mm),box("Tipp 1 - sanft",s.get("hint_1"),st,PALE_YELLOW,border=GOLD),Spacer(1,3*mm),box("Tipp 2 - deutlich",s.get("hint_2"),st,PALE_RED,border=colors.HexColor("#D9A0A0")),PageBreak()]

    story += [badge("FINALE",st,bg=GOLD,fg=PURPLE_DARK),Spacer(1,4*mm),Paragraph("Der Schatz ist zum Greifen nah",st["h1"]),box("Zum Vorlesen",q.get("finale"),st,CREAM,border=GOLD),Spacer(1,8*mm),Paragraph("10-Minuten-Bonus",st["h2"]),box((q.get("bonus_game") or {}).get("title"),(q.get("bonus_game") or {}).get("instructions"),st,LAVENDER),PageBreak()]

    story += parent_header("Lösungen und Route auf einen Blick",st)
    rows=[[Paragraph("<b>Nr.</b>",st["small"]),Paragraph("<b>Ort</b>",st["small"]),Paragraph("<b>Lösung</b>",st["small"]),Paragraph("<b>Weiter</b>",st["small"])]]
    for s in q.get("stations") or []: rows.append([Paragraph(str(s.get("number")),st["small"]),Paragraph(safe(s.get("current_location")),st["small"]),Paragraph(safe(s.get("solution")),st["small"]),Paragraph(safe(s.get("next_location")),st["small"])])
    sol=Table(rows,colWidths=[13*mm,42*mm,73*mm,40*mm],repeatRows=1); sol.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),PURPLE_DARK),("TEXTCOLOR",(0,0),(-1,0),WHITE),("GRID",(0,0),(-1,-1),0.35,LINE),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),5)])); story += [sol,Spacer(1,6*mm),Paragraph("Routencheck",st["h2"])]
    for item in q.get("route_check") or []: story.append(Paragraph("OK - "+safe(item),st["body"]))
    metrics=(q.get("quality_gate") or {}).get("metrics") or {}; story += [Spacer(1,3*mm),box("Automatischer Qualitätscheck",f"Bestanden: {metrics.get('puzzle_types','?')} Rätseltypen, {metrics.get('team_stations','?')} Teamstationen, {metrics.get('station_minutes','?')} Stationsminuten, Aufbau {metrics.get('setup_minutes','?')} Min.",st,PALE_GREEN,border=colors.HexColor("#9AC6A3")),PageBreak()]
    story += [CertificateArtwork(payload.get("child_name"),payload.get("theme"),q.get("certificate_text"))]
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return buf.getvalue()
