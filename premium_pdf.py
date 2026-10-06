import html
import io
import math
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

WHITE = colors.white
INK = colors.HexColor('#221b18')
MUTED = colors.HexColor('#746b64')
CREAM = colors.HexColor('#FFF9EC')
PAPER = colors.HexColor('#FFFDF7')
LINE = colors.HexColor('#E5D4B8')
WOOD = colors.HexColor('#D99954')
WOOD_LIGHT = colors.HexColor('#F0BD7A')
WOOD_DARK = colors.HexColor('#8E4F20')
RED = colors.HexColor('#E45D49')
GOLD = colors.HexColor('#D6A329')

THEMES = {
    'detective': dict(main='#4A3F52', dark='#26212B', accent='#D7B56D', pale='#F0EBE2', label='DETEKTIVMISSION', title='MEISTERDETEKTIV', motif='detective'),
    'dino': dict(main='#23814C', dark='#0E4D2D', accent='#E4B44B', pale='#E8F4DE', label='DINOSAURIEREXPEDITION', title='DINO-ENTDECKER', motif='dino'),
    'space': dict(main='#2E71AE', dark='#18325F', accent='#F0C55A', pale='#E7F2FB', label='WELTRAUMMISSION', title='STERNENKOMMANDANT', motif='space'),
    'magic': dict(main='#7E4EAA', dark='#48245F', accent='#F1C85B', pale='#F3EAF9', label='ZAUBERSCHULE', title='MEISTERZAUBERER', motif='magic'),
    'animal': dict(main='#D47740', dark='#7D4125', accent='#EDC66B', pale='#FCECDD', label='TIERRETTER-MISSION', title='EHREN-TIERRETTER', motif='animal'),
    'research': dict(main='#2D7B70', dark='#174B44', accent='#E5B84C', pale='#E8F4EF', label='FORSCHER-MISSION', title='MEISTERFORSCHER', motif='research'),
}

def safe(v):
    return html.escape(str(v or '')).replace('\n','<br/>')

def detect_theme(value):
    v=(value or '').lower()
    if 'detektiv' in v: k='detective'
    elif 'dino' in v: k='dino'
    elif 'weltraum' in v or 'space' in v: k='space'
    elif 'zauber' in v or 'mag' in v: k='magic'
    elif 'tier' in v: k='animal'
    else: k='research'
    d=dict(THEMES[k]); d['key']=k
    for c in ('main','dark','accent','pale'): d[c]=colors.HexColor(d[c])
    return d

def wrap(c,text,font,size,width):
    lines=[]; cur=''
    for word in str(text or '').split():
        test=(cur+' '+word).strip()
        if cur and c.stringWidth(test,font,size)>width:
            lines.append(cur); cur=word
        else: cur=test
    if cur: lines.append(cur)
    return lines

def star(c,cx,cy,r,fill=GOLD):
    c.setFillColor(fill); pts=[]
    for i in range(10):
        a=-math.pi/2+i*math.pi/5; rr=r if i%2==0 else r*.42
        pts.append((cx+math.cos(a)*rr,cy+math.sin(a)*rr))
    p=c.beginPath(); p.moveTo(*pts[0])
    for pt in pts[1:]: p.lineTo(*pt)
    p.close(); c.drawPath(p,stroke=0,fill=1)

def wood_sign(c,x,y,w,h,text,size=18):
    c.setFillColor(WOOD_DARK); c.roundRect(x+2*mm,y-2*mm,w,h,5*mm,stroke=0,fill=1)
    c.setFillColor(WOOD_LIGHT); c.setStrokeColor(WOOD_DARK); c.setLineWidth(1.2)
    c.roundRect(x,y,w,h,5*mm,stroke=1,fill=1)
    c.setStrokeColor(colors.HexColor('#B7773C')); c.setLineWidth(.6)
    for yy in (y+h*.28,y+h*.62): c.line(x+5*mm,yy,x+w-5*mm,yy)
    for xx in (x+5*mm,x+w-6*mm):
        c.setFillColor(colors.HexColor('#6E421D')); c.circle(xx,y+h-5*mm,1.1*mm,stroke=0,fill=1)
    c.setFillColor(colors.HexColor('#17100B')); c.setFont('Helvetica-Bold',size)
    lines=wrap(c,text,'Helvetica-Bold',size,w-14*mm)
    yy=y+h/2+(len(lines)-1)*size*.45
    for ln in lines[:3]: c.drawCentredString(x+w/2,yy,ln); yy-=size*1.08

def parchment(c,x,y,w,h,stroke=LINE,fill=PAPER,r=4*mm):
    c.setFillColor(fill); c.setStrokeColor(stroke); c.setLineWidth(1)
    c.roundRect(x,y,w,h,r,stroke=1,fill=1)
    c.setStrokeColor(colors.Color(stroke.red,stroke.green,stroke.blue,alpha=.45))
    c.line(x+6*mm,y+h-3*mm,x+w-8*mm,y+h-3*mm)

def draw_motif(c,theme,cx,cy,s=1.0):
    main,dark,accent=theme['main'],theme['dark'],theme['accent']
    c.saveState(); c.setLineCap(1); c.setLineJoin(1)
    m=theme['motif']
    if m=='detective':
        c.setStrokeColor(dark); c.setLineWidth(4*s); c.circle(cx-4*s,cy+3*s,12*s,stroke=1,fill=0); c.line(cx+4*s,cy-5*s,cx+17*s,cy-18*s)
        c.setStrokeColor(accent); c.setLineWidth(1.5*s); c.circle(cx-4*s,cy+3*s,7*s,stroke=1,fill=0)
    elif m=='dino':
        c.setFillColor(main); c.ellipse(cx-16*s,cy-10*s,cx+16*s,cy+8*s,stroke=0,fill=1)
        c.circle(cx+13*s,cy+7*s,7*s,stroke=0,fill=1); c.setFillColor(PAPER); c.circle(cx+15*s,cy+9*s,1.5*s,stroke=0,fill=1)
        c.setFillColor(main); c.rect(cx-9*s,cy-17*s,5*s,10*s,stroke=0,fill=1); c.rect(cx+4*s,cy-17*s,5*s,10*s,stroke=0,fill=1)
        c.setStrokeColor(main); c.setLineWidth(5*s); c.line(cx-14*s,cy,cx-24*s,cy+8*s)
    elif m=='space':
        c.setFillColor(main); c.circle(cx,cy,14*s,stroke=0,fill=1); c.setStrokeColor(accent); c.setLineWidth(2*s); c.ellipse(cx-24*s,cy-7*s,cx+24*s,cy+7*s,stroke=1,fill=0)
        star(c,cx+23*s,cy+18*s,4*s,accent); star(c,cx-20*s,cy-15*s,2.7*s,accent)
    elif m=='magic':
        c.setStrokeColor(dark); c.setLineWidth(4*s); c.line(cx-15*s,cy-14*s,cx+11*s,cy+12*s); star(c,cx+14*s,cy+15*s,6*s,accent)
        star(c,cx-13*s,cy+12*s,3*s,main); star(c,cx+18*s,cy-8*s,2.4*s,main)
    elif m=='animal':
        c.setFillColor(main); c.circle(cx,cy-5*s,9*s,stroke=0,fill=1)
        for dx,dy,r in [(-11,7,4),(0,11,4),(11,7,4),(-17,-1,3.5)]: c.circle(cx+dx*s,cy+dy*s,r*s,stroke=0,fill=1)
    else:
        c.setStrokeColor(dark); c.setLineWidth(2*s); c.circle(cx,cy,16*s,stroke=1,fill=0); c.line(cx,cy-14*s,cx,cy+14*s); c.line(cx-14*s,cy,cx+14*s,cy)
        p=c.beginPath(); p.moveTo(cx,cy+12*s); p.lineTo(cx+5*s,cy); p.lineTo(cx,cy-4*s); p.lineTo(cx-5*s,cy); p.close(); c.setFillColor(main); c.drawPath(p,stroke=0,fill=1)
    c.restoreState()

class CoverArt(Flowable):
    def __init__(self,payload,q):
        super().__init__(); self.width=174*mm; self.height=222*mm; self.p=payload; self.q=q; self.t=detect_theme(payload.get('theme'))
    def draw(self):
        c,w,h=self.canv,self.width,self.height; t=self.t
        c.setFillColor(CREAM); c.roundRect(0,0,w,h,7*mm,stroke=0,fill=1)
        c.setFillColor(t['pale'])
        for x,y,r in [(8,205,13),(26,214,9),(150,211,12),(166,196,11),(7,24,12),(161,20,13)]: c.circle(x*mm,y*mm,r*mm,stroke=0,fill=1)
        wood_sign(c,13*mm,h-61*mm,w-26*mm,43*mm,'DEINE PERSÖNLICHE GEBURTSTAGSQUEST',18)
        parchment(c,14*mm,25*mm,w-28*mm,h-94*mm,stroke=colors.HexColor('#E1C99E'))
        c.setFillColor(t['pale']); c.roundRect(w-72*mm,h-132*mm,50*mm,55*mm,12*mm,stroke=0,fill=1)
        draw_motif(c,t,w-47*mm,h-102*mm,2.25)
        c.setFillColor(t['main']); c.setFont('Helvetica-Bold',8); c.drawString(25*mm,h-88*mm,t['label'])
        title=self.q.get('title') or f"{self.p.get('child_name','Dein Kind')}s Geburtstags-Abenteuer"
        c.setFillColor(t['dark']); c.setFont('Helvetica-Bold',23); yy=h-104*mm
        for ln in wrap(c,title,'Helvetica-Bold',23,88*mm)[:4]: c.drawString(25*mm,yy,ln); yy-=10*mm
        sub=self.q.get('subtitle') or 'Eine ganz persönliche Schatzsuche zum Kindergeburtstag'
        c.setFillColor(MUTED); c.setFont('Helvetica',10); yy-=2*mm
        for ln in wrap(c,sub,'Helvetica',10,88*mm)[:3]: c.drawString(25*mm,yy,ln); yy-=5*mm
        age=self.p.get('age','?'); group=self.p.get('group_size','?'); setup=self.q.get('setup_minutes',15)
        labels=[f"{age} Jahre",f"{group} Kinder","8 Stationen",f"ca. {setup} Min. Aufbau"]
        bx=25*mm; by=48*mm
        for i,lab in enumerate(labels):
            x=bx+(i%2)*60*mm; y=by-(i//2)*14*mm
            c.setFillColor(t['main']); c.roundRect(x,y,52*mm,10*mm,5*mm,stroke=0,fill=1); c.setFillColor(WHITE); c.setFont('Helvetica-Bold',7.7); c.drawCentredString(x+26*mm,y+3.5*mm,str(lab))
        c.setFillColor(t['dark']); c.setFont('Helvetica-Bold',9); c.drawCentredString(w/2,18*mm,'AUSDRUCKEN  -  VERSTECKEN  -  LOSSPIELEN')

class HeaderBand(Flowable):
    def __init__(self,title,theme,subtitle=None):
        super().__init__(); self.width=168*mm; self.height=34*mm; self.title=title; self.t=detect_theme(theme); self.subtitle=subtitle
    def draw(self):
        c,w,h=self.canv,self.width,self.height;t=self.t
        wood_sign(c,0,2*mm,w,h-2*mm,self.title,16)
        c.setFillColor(t['main']); c.circle(12*mm,h-7*mm,7*mm,stroke=0,fill=1); draw_motif(c,t,12*mm,h-7*mm,.38)

class ThreeSteps(Flowable):
    def __init__(self,theme): super().__init__(); self.width=168*mm; self.height=44*mm; self.t=detect_theme(theme)
    def draw(self):
        c,w,h=self.canv,self.width,self.height;t=self.t
        parchment(c,0,0,w,h,stroke=colors.HexColor('#DFC99F'))
        items=[('1','DRUCKEN'),('2','VERSTECKEN'),('3','LOSSPIELEN')]; xs=[28,84,140]
        for (num,label),x in zip(items,xs):
            c.setFillColor(t['main']); c.circle(x*mm,25*mm,8*mm,stroke=0,fill=1); c.setFillColor(WHITE); c.setFont('Helvetica-Bold',12); c.drawCentredString(x*mm,22.8*mm,num)
            c.setFillColor(INK); c.setFont('Helvetica-Bold',8); c.drawCentredString(x*mm,8*mm,label)
        c.setStrokeColor(t['main']); c.setLineWidth(2); c.line(38*mm,25*mm,73*mm,25*mm); c.line(95*mm,25*mm,130*mm,25*mm)

class ChildCardArt(Flowable):
    def __init__(self,station,theme,child):
        super().__init__(); self.width=168*mm; self.height=182*mm; self.s=station; self.t=detect_theme(theme); self.child=child
    def draw(self):
        c,w,h=self.canv,self.width,self.height;s=self.s;t=self.t
        parchment(c,0,0,w,h,stroke=colors.HexColor('#D9C197'))
        c.setFillColor(t['pale']); c.circle(12*mm,h-12*mm,16*mm,stroke=0,fill=1); c.circle(w-9*mm,11*mm,14*mm,stroke=0,fill=1)
        draw_motif(c,t,w-20*mm,h-22*mm,.72)
        n=s.get('number','?'); title=s.get('title') or f'Station {n}'
        c.setFillColor(t['main']); c.circle(15*mm,h-22*mm,9*mm,stroke=0,fill=1); c.setFillColor(WHITE); c.setFont('Helvetica-Bold',14); c.drawCentredString(15*mm,h-25*mm,str(n))
        c.setFillColor(t['dark']); c.setFont('Helvetica-Bold',18); yy=h-19*mm
        for ln in wrap(c,title,'Helvetica-Bold',18,115*mm)[:2]: c.drawString(30*mm,yy,ln); yy-=8*mm
        c.setFillColor(t['main']); c.setFont('Helvetica-Bold',7.5); c.drawString(30*mm,yy-1*mm,'FÜR DIE KINDER - AUSSCHNEIDEN')
        yy-=14*mm
        story=s.get('story') or s.get('child_card') or ''
        c.setFillColor(INK); c.setFont('Helvetica',10)
        for ln in wrap(c,story,'Helvetica',10,w-28*mm)[:6]: c.drawString(14*mm,yy,ln); yy-=5*mm
        yy-=3*mm
        role=s.get('team_role') or 'Spurenteam'
        role_y=yy-13*mm
        c.setFillColor(t['pale']); c.roundRect(14*mm,role_y,w-28*mm,11*mm,5*mm,stroke=0,fill=1); c.setFillColor(t['dark']); c.setFont('Helvetica-Bold',9); c.drawString(20*mm,role_y+3.7*mm,f"TEAMROLLE: {role}")
        yy=role_y-8*mm
        c.setFillColor(colors.white); c.setStrokeColor(t['main']); c.setLineWidth(1.4); c.roundRect(12*mm,26*mm,w-24*mm,max(44*mm,yy-25*mm),6*mm,stroke=1,fill=1)
        c.setFillColor(t['main']); c.setFont('Helvetica-Bold',11); c.drawString(20*mm,yy-5*mm,'EURE AUFGABE')
        task=s.get('puzzle_display') or s.get('task') or s.get('child_card') or 'Löst das Rätsel gemeinsam.'
        c.setFillColor(INK); c.setFont('Helvetica-Bold',10); ty=yy-15*mm
        for ln in wrap(c,task,'Helvetica-Bold',10,w-42*mm)[:16]: c.drawString(20*mm,ty,ln); ty-=5.2*mm
        c.setFillColor(t['dark']); c.setFont('Helvetica-Bold',8); c.drawCentredString(w/2,12*mm,'Wenn ihr die Lösung habt, kennt ihr den nächsten Ort!')

class CertificateArt(Flowable):
    def __init__(self,payload,q): super().__init__(); self.width=174*mm; self.height=220*mm; self.p=payload; self.q=q; self.t=detect_theme(payload.get('theme'))
    def draw(self):
        c,w,h=self.canv,self.width,self.height;t=self.t
        c.setFillColor(CREAM); c.roundRect(0,0,w,h,5*mm,stroke=0,fill=1)
        c.setStrokeColor(t['dark']); c.setLineWidth(3); c.roundRect(5*mm,5*mm,w-10*mm,h-10*mm,5*mm,stroke=1,fill=0)
        c.setStrokeColor(t['accent']); c.setLineWidth(1.4); c.roundRect(10*mm,10*mm,w-20*mm,h-20*mm,4*mm,stroke=1,fill=0)
        for x,y in [(17,18),(157,18),(17,202),(157,202)]: star(c,x*mm,y*mm,4*mm,t['accent'])
        draw_motif(c,t,w/2,h-45*mm,1.4)
        wood_sign(c,32*mm,h-91*mm,w-64*mm,25*mm,'URKUNDE',22)
        c.setFillColor(MUTED); c.setFont('Helvetica',10); c.drawCentredString(w/2,h-106*mm,'Diese Auszeichnung geht an')
        name=self.p.get('child_name') or 'Geburtstagsheld'
        c.setFillColor(t['dark']); c.setFont('Helvetica-Bold',27); c.drawCentredString(w/2,h-124*mm,str(name))
        c.setStrokeColor(t['accent']); c.line(34*mm,h-131*mm,w-34*mm,h-131*mm)
        text=self.q.get('certificate_text') or 'hat gemeinsam mit dem Team alle acht Stationen gemeistert, knifflige Rätsel gelöst und den Schatz gefunden.'
        c.setFillColor(INK); c.setFont('Helvetica',11); yy=h-146*mm
        for ln in wrap(c,text,'Helvetica',11,w-42*mm)[:6]: c.drawCentredString(w/2,yy,ln); yy-=6*mm
        c.setFillColor(t['main']); c.circle(w/2,49*mm,20*mm,stroke=0,fill=1); c.setStrokeColor(t['accent']); c.setLineWidth(2); c.circle(w/2,49*mm,15*mm,stroke=1,fill=0); star(c,w/2,54*mm,6*mm,t['accent'])
        c.setFillColor(WHITE); c.setFont('Helvetica-Bold',7.3); c.drawCentredString(w/2,40*mm,t['title'])
        c.setStrokeColor(LINE); c.line(27*mm,24*mm,72*mm,24*mm); c.line(w-72*mm,24*mm,w-27*mm,24*mm)
        c.setFillColor(MUTED); c.setFont('Helvetica',8); c.drawCentredString(49.5*mm,18*mm,'Datum'); c.drawCentredString(w-49.5*mm,18*mm,'Unterschrift')

def styles(theme):
    t=detect_theme(theme); b=getSampleStyleSheet()
    return {
      'eyebrow':ParagraphStyle('eyebrow',parent=b['BodyText'],fontName='Helvetica-Bold',fontSize=8,leading=10,textColor=t['main'],spaceAfter=5),
      'h1':ParagraphStyle('h1',parent=b['Heading1'],fontName='Helvetica-Bold',fontSize=20,leading=24,textColor=t['dark'],spaceAfter=9),
      'h2':ParagraphStyle('h2',parent=b['Heading2'],fontName='Helvetica-Bold',fontSize=14,leading=18,textColor=t['main'],spaceBefore=6,spaceAfter=5),
      'body':ParagraphStyle('body',parent=b['BodyText'],fontSize=10.3,leading=14.5,textColor=INK,spaceAfter=6),
      'small':ParagraphStyle('small',parent=b['BodyText'],fontSize=8.5,leading=12,textColor=MUTED,spaceAfter=3),
      'center':ParagraphStyle('center',parent=b['BodyText'],fontSize=10.3,leading=14.5,textColor=INK,alignment=TA_CENTER,spaceAfter=5),
    }

def box(label,content,st,theme,bg=None):
    t=detect_theme(theme); bg=bg or t['pale']
    p=Paragraph(f"<b>{safe(label)}</b><br/>{safe(content)}",st['body'])
    tb=Table([[p]],colWidths=[168*mm]); tb.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),bg),('BOX',(0,0),(-1,-1),.8,t['main']),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)])); return tb

def page_title(story,title,theme,subtitle=None):
    story += [HeaderBand(title,theme,subtitle),Spacer(1,7*mm)]
    if subtitle: story += [Paragraph(safe(subtitle),styles(theme)['small']),Spacer(1,2*mm)]

def footer(canvas,doc):
    canvas.saveState(); width,_=A4; canvas.setStrokeColor(LINE); canvas.line(18*mm,13*mm,width-18*mm,13*mm); canvas.setFillColor(MUTED); canvas.setFont('Helvetica',8); canvas.drawString(18*mm,8*mm,'GeburtstagsQuest - Dein persönliches Abenteuer'); canvas.drawRightString(width-18*mm,8*mm,f'Seite {doc.page}'); canvas.restoreState()

def station_hint(s,key,fallback=''):
    return s.get(key) or s.get('hint') or fallback

def build_premium_pdf(payload,q):
    buf=io.BytesIO(); theme=payload.get('theme'); st=styles(theme); t=detect_theme(theme)
    doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=18*mm,bottomMargin=18*mm,title='GeburtstagsQuest')
    story=[CoverArt(payload,q),PageBreak()]
    page_title(story,'So funktioniert eure GeburtstagsQuest',theme)
    story += [Paragraph('Diese Quest wurde speziell für euer Geburtstagskind, die Gruppe und eure ausgewählten Spielorte erstellt. Ihr müsst nur noch drucken, verstecken und den Schatz vorbereiten.',st['body']),Spacer(1,3*mm),ThreeSteps(theme),Spacer(1,6*mm)]
    setup=q.get('setup_minutes',15)
    story += [box('Euer Ziel',f'Plant etwa {setup} Minuten für den Aufbau ein. Während des Spiels sollt ihr möglichst nur vorlesen und bei Bedarf Hinweise geben.',st,theme),Spacer(1,5*mm),box('Wichtig','Elternseiten enthalten Lösungen und Verstecke. Diese Seiten bitte nicht den Kindern zeigen.',st,theme,bg=colors.HexColor('#FFF0E6')),PageBreak()]
    page_title(story,'Was muss ich drucken?',theme)
    print_rows=[['KINDERKARTEN','Ausschneiden und an den angegebenen Orten verstecken'],['ELTERNSEITEN','Vorbereitung, Lösungen und Hinweise - nicht zeigen'],['URKUNDE','Für das Finale bereithalten'],['BONUSMISSION','Optional, falls noch Zeit bleibt']]
    tb=Table([[Paragraph(f'<b>{a}</b>',st['body']),Paragraph(b,st['body'])] for a,b in print_rows],colWidths=[49*mm,119*mm]); tb.setStyle(TableStyle([('BACKGROUND',(0,0),(0,-1),t['pale']),('GRID',(0,0),(-1,-1),.6,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)])); story += [tb,PageBreak()]
    page_title(story,'Ein entspannter Geburtstagsnachmittag',theme)
    schedule=q.get('party_schedule') or ['Ankommen & Begrüßung','Kuchen & Geschenke','GeburtstagsQuest starten','Schatz & Urkunde','Bonusspiel oder freies Spielen']
    if isinstance(schedule,str): schedule=[x.strip() for x in schedule.split('\n') if x.strip()]
    rows=[]
    for i,item in enumerate(schedule[:6],1): rows.append([Paragraph(f'<b>{i}</b>',st['center']),Paragraph(safe(item),st['body'])])
    tb=Table(rows,colWidths=[18*mm,150*mm]); tb.setStyle(TableStyle([('BACKGROUND',(0,0),(0,-1),t['main']),('TEXTCOLOR',(0,0),(0,-1),WHITE),('GRID',(0,0),(-1,-1),.6,LINE),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LEFTPADDING',(0,0),(-1,-1),8)])); story += [tb,Spacer(1,6*mm),Paragraph('Die Zeiten könnt ihr natürlich an euren Geburtstag anpassen.',st['small']),PageBreak()]
    page_title(story,'Material & Schatzideen',theme)
    mats=q.get('materials') or ['Ausgedruckte Quest','Schere','Stifte','Klebeband','Ein Schatz oder kleine Mitgebsel']
    for m in mats: story += [box('MATERIAL',m,st,theme),Spacer(1,3*mm)]
    story += [Spacer(1,3*mm),Paragraph('<b>Schatzideen:</b> kleine Sticker, Edelsteine, Mini-Figuren, Medaillen oder Mitgebsel - alles optional.',st['body']),PageBreak()]
    page_title(story,'Vorbereitung & Versteckplan',theme)
    prep=q.get('preparation') or []
    if prep:
        data=[['Station','Ort','Verstecken / vorbereiten']]
        for p in prep[:10]: data.append([str(p.get('station','')),str(p.get('location','')),str(p.get('hide') or p.get('item') or '')])
        tb=Table([[Paragraph(safe(x),st['small']) for x in row] for row in data],colWidths=[22*mm,43*mm,103*mm],repeatRows=1); tb.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),t['dark']),('TEXTCOLOR',(0,0),(-1,0),WHITE),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('GRID',(0,0),(-1,-1),.5,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),6)])); story += [tb]
    else: story += [Paragraph('Lege jede Kinderkarte am angegebenen Ort bereit. Platziere den Schatz am gewählten Finalort.',st['body'])]
    story += [PageBreak()]
    page_title(story,'Die Route auf einen Blick',theme)
    stations=q.get('stations') or []
    route=[]
    for s in stations: route.append(s.get('current_location') or s.get('location') or f"Station {s.get('number','')}")
    if stations: route.append(stations[-1].get('next_location') or payload.get('final_location') or 'Schatz')
    if route: story += [box('ROUTE','  ->  '.join(str(x) for x in route if x),st,theme),Spacer(1,5*mm)]
    story += [box('DEIN JOB','Lass die Kinder möglichst selbst lösen. Nutze erst Tipp 1 und danach Tipp 2. Achte darauf, dass verschiedene Kinder eine Rolle übernehmen.',st,theme),PageBreak()]
    page_title(story,'Die Mission beginnt',theme)
    intro=q.get('intro_story') or 'Heute beginnt ein ganz besonderes Abenteuer. Nur euer Team kann die geheime Mission lösen.'
    story += [Paragraph(safe(intro),ParagraphStyle('intro',parent=st['body'],fontSize=13,leading=19,textColor=INK)),Spacer(1,8*mm),box('STARTSIGNAL',f"{payload.get('child_name','Geburtstagskind')}, eure Mission beginnt jetzt! Findet die erste Spur.",st,theme),PageBreak()]
    for idx,s in enumerate(stations,1):
        if 'number' not in s: s=dict(s); s['number']=idx
        story += [ChildCardArt(s,theme,payload.get('child_name')),PageBreak()]
        page_title(story,f"Station {s.get('number',idx)} - Nur für Eltern",theme)
        current=s.get('current_location') or s.get('location') or '-'; nxt=s.get('next_location') or '-'; dur=s.get('duration') or 'ca. 5 Min.'
        meta=Table([[Paragraph('<b>Aktueller Ort</b>',st['small']),Paragraph('<b>Nächster Ort</b>',st['small']),Paragraph('<b>Dauer</b>',st['small'])],[Paragraph(safe(current),st['body']),Paragraph(safe(nxt),st['body']),Paragraph(safe(dur),st['body'])]],colWidths=[58*mm,58*mm,52*mm]); meta.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),t['pale']),('GRID',(0,0),(-1,-1),.5,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),6)])); story += [meta,Spacer(1,5*mm)]
        story += [box('LÖSUNG',s.get('solution') or 'Siehe Aufgabenlogik.',st,theme),Spacer(1,3*mm),box('TIPP 1',station_hint(s,'hint1','Gebt einen kleinen Denkanstoß, ohne die Lösung zu verraten.'),st,theme,bg=colors.HexColor('#FFF6D8')),Spacer(1,3*mm),box('TIPP 2',station_hint(s,'hint2','Lenkt die Kinder deutlicher auf den entscheidenden Teil des Rätsels.'),st,theme,bg=colors.HexColor('#FFE9D9')),Spacer(1,3*mm),box('DEIN JOB AN DIESER STATION','Kinder zuerst selbst lösen lassen. Nur bei Bedarf Tipps einsetzen und darauf achten, dass die Teamrolle wirklich wechselt.',st,theme),PageBreak()]
    page_title(story,'Ihr habt es geschafft!',theme)
    finale=q.get('finale') or f"Alle Spuren sind gefunden. Der Schatz wartet am vereinbarten Finalort: {payload.get('final_location','eurem Schatzort')}."
    story += [Paragraph(safe(finale),ParagraphStyle('finale',parent=st['body'],fontSize=13,leading=19,textColor=INK,alignment=TA_CENTER)),Spacer(1,8*mm),box('JETZT','Schatz öffnen, jubeln und die Urkunde überreichen!',st,theme),PageBreak()]
    page_title(story,'Bonus-Mission',theme)
    bonus=q.get('bonus_game') or 'Erfindet gemeinsam einen Teamruf und führt eine kurze Sieger-Challenge durch.'
    story += [Paragraph(safe(bonus),st['body']),Spacer(1,6*mm),box('OPTIONAL','Ideal, wenn die Quest schneller endet als geplant oder die Kinder noch Energie haben.',st,theme),PageBreak()]
    page_title(story,'Lösungsübersicht - Nur für Eltern',theme)
    data=[['Station','Lösung','Nächster Ort']]
    for s in stations: data.append([str(s.get('number','')),str(s.get('solution','')),str(s.get('next_location',''))])
    if len(data)>1:
        tb=Table([[Paragraph(safe(x),st['small']) for x in row] for row in data],colWidths=[22*mm,92*mm,54*mm],repeatRows=1); tb.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),t['dark']),('TEXTCOLOR',(0,0),(-1,0),WHITE),('GRID',(0,0),(-1,-1),.5,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('LEFTPADDING',(0,0),(-1,-1),5)])); story += [tb]
    story += [PageBreak()]
    page_title(story,'Regen? Kein Problem!',theme)
    indoor=q.get('indoor_plan') or q.get('route_check') or 'Wenn ein Außenort nicht funktioniert, übergib die nächste Karte direkt oder nutze nur einen vom Bestellformular erlaubten Innenort. Die Geschichte kann ohne Unterbrechung weitergehen.'
    if isinstance(indoor,(list,tuple)): indoor='\n'.join(map(str,indoor))
    story += [Paragraph(safe(indoor),st['body']),Spacer(1,5*mm),box('WICHTIG','Keine nicht freigegebenen Räume spontan in die Route aufnehmen.',st,theme),PageBreak()]
    page_title(story,'Wenn etwas anders läuft als geplant',theme)
    faqs=[('Die Kinder hängen fest','Erst Tipp 1 geben. Wenn nötig danach Tipp 2.'),('Die Kinder sind zu schnell','Bonus-Mission nutzen oder das Finale gemeinsam zelebrieren.'),('Ein Versteck funktioniert nicht','Karte direkt übergeben und die Geschichte fortsetzen.'),('Ein Kind löst alles','Die nächste Teamrolle gezielt an ein anderes Kind vergeben.')]
    for a,b in faqs: story += [box(a,b,st,theme),Spacer(1,3*mm)]
    story += [PageBreak(),CertificateArt(payload,q)]
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return buf.getvalue()
