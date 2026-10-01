import io
import math

from PIL import Image, ImageDraw
from flask import Response
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader


THEMES = {
    "detective": {"sky": "#F6E8CF", "main": "#5B465B", "accent": "#D7A84B", "green": "#567B43"},
    "dino": {"sky": "#DFF2C8", "main": "#23814C", "accent": "#F0A23A", "green": "#2F8B49"},
    "space": {"sky": "#17264F", "main": "#2E71AE", "accent": "#F0C55A", "green": "#5367B7"},
    "magic": {"sky": "#E7D7F4", "main": "#7E4EAA", "accent": "#F1C85B", "green": "#6A4B93"},
    "animal": {"sky": "#E8F5D8", "main": "#D47740", "accent": "#F0C45E", "green": "#4E8B48"},
    "research": {"sky": "#D8F0E8", "main": "#2D7B70", "accent": "#E5B84C", "green": "#3C8363"},
}


def _hex(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def _theme_key(value):
    value = str(value or "").lower()
    if value in THEMES:
        return value
    if "detektiv" in value:
        return "detective"
    if "dino" in value:
        return "dino"
    if "weltraum" in value or "space" in value:
        return "space"
    if "zauber" in value or "magic" in value:
        return "magic"
    if "tier" in value or "animal" in value:
        return "animal"
    return "research"


def _ellipse(draw, box, fill, outline=None, width=1):
    draw.ellipse(tuple(int(v) for v in box), fill=fill, outline=outline, width=width)


def _round(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(tuple(int(v) for v in box), radius=int(radius), fill=fill, outline=outline, width=width)


def _leaf(draw, x, y, s, color, angle=0):
    pts = [(-1.0, 0), (-0.25, -0.6), (0.7, -0.45), (1.0, 0), (0.25, 0.6), (-0.7, 0.45)]
    ca, sa = math.cos(angle), math.sin(angle)
    transformed = []
    for px, py in pts:
        rx = (px * ca - py * sa) * s + x
        ry = (px * sa + py * ca) * s + y
        transformed.append((rx, ry))
    draw.polygon(transformed, fill=color)


def _spark(draw, x, y, r, color):
    pts = []
    for i in range(8):
        ang = math.pi / 4 * i
        rr = r if i % 2 == 0 else r * 0.3
        pts.append((x + math.cos(ang) * rr, y + math.sin(ang) * rr))
    draw.polygon(pts, fill=color)


def _background(draw, size, cfg, key):
    sky = _hex(cfg["sky"])
    cream = (255, 249, 236)
    if key == "space":
        top, bottom = _hex("#111936"), _hex("#284A83")
    else:
        top, bottom = _mix(sky, cream, 0.08), _mix(sky, cream, 0.56)
    for y in range(size):
        c = _mix(top, bottom, y / max(1, size - 1))
        draw.line((0, y, size, y), fill=c)
    if key == "space":
        for x, y, r in [(60, 62, 4), (130, 40, 3), (245, 74, 5), (355, 48, 3), (438, 96, 4), (94, 170, 3), (405, 190, 3)]:
            _spark(draw, x * size / 512, y * size / 512, r * size / 512, (255, 236, 167))
    else:
        green = _hex(cfg["green"])
        for x, y, s, a in [(30, 44, 34, .3), (72, 22, 28, -.5), (470, 48, 34, 2.7), (442, 20, 27, 3.4), (22, 448, 38, -.1), (477, 456, 38, 3.0)]:
            _leaf(draw, x * size / 512, y * size / 512, s * size / 512, green, a)


def _draw_child(draw, size, cfg, key):
    scale = size / 512
    main = _hex(cfg["main"])
    dark = tuple(max(0, c - 45) for c in main)
    skin = (246, 190, 139)
    hair = (103, 64, 36)
    # backpack/body
    _round(draw, (132*scale, 286*scale, 366*scale, 500*scale), 60*scale, (190, 139, 79))
    _round(draw, (175*scale, 292*scale, 337*scale, 493*scale), 56*scale, (213, 171, 114))
    # neck and face
    _round(draw, (223*scale, 235*scale, 289*scale, 320*scale), 24*scale, skin)
    _ellipse(draw, (168*scale, 83*scale, 346*scale, 280*scale), skin)
    # hair mass
    _ellipse(draw, (156*scale, 71*scale, 354*scale, 210*scale), hair)
    _ellipse(draw, (166*scale, 102*scale, 220*scale, 273*scale), hair)
    _ellipse(draw, (294*scale, 108*scale, 348*scale, 272*scale), hair)
    # face overlay to expose forehead
    _ellipse(draw, (179*scale, 104*scale, 334*scale, 277*scale), skin)
    # explorer hat / theme headwear
    if key in ("detective", "dino", "research", "animal"):
        _ellipse(draw, (151*scale, 60*scale, 361*scale, 118*scale), (205, 170, 113))
        _round(draw, (186*scale, 33*scale, 328*scale, 111*scale), 30*scale, (229, 199, 143), outline=(125, 84, 49), width=max(1,int(3*scale)))
        draw.line((194*scale, 80*scale, 319*scale, 80*scale), fill=(139, 91, 52), width=max(1,int(5*scale)))
    elif key == "magic":
        draw.polygon([(166*scale, 111*scale), (259*scale, 18*scale), (344*scale, 116*scale)], fill=dark)
        _ellipse(draw, (145*scale, 96*scale, 365*scale, 134*scale), dark)
        _spark(draw, 260*scale, 59*scale, 12*scale, _hex(cfg["accent"]))
    else:
        # astronaut helmet ring
        _ellipse(draw, (149*scale, 55*scale, 363*scale, 292*scale), (226, 235, 245), outline=(80, 105, 137), width=max(1,int(8*scale)))
        _ellipse(draw, (171*scale, 78*scale, 341*scale, 268*scale), skin)
    # eyes
    for ex in (224, 286):
        _ellipse(draw, ((ex-18)*scale, 158*scale, (ex+18)*scale, 199*scale), (255,255,255))
        _ellipse(draw, ((ex-6)*scale, 168*scale, (ex+8)*scale, 190*scale), (66,47,35))
        _ellipse(draw, ((ex-1)*scale, 171*scale, (ex+4)*scale, 177*scale), (255,255,255))
    # nose and smile
    draw.arc((235*scale, 181*scale, 277*scale, 235*scale), start=15, end=165, fill=(170,83,65), width=max(1,int(3*scale)))
    draw.arc((221*scale, 198*scale, 300*scale, 253*scale), start=12, end=168, fill=(135,57,52), width=max(1,int(5*scale)))
    # arms
    draw.line((190*scale, 331*scale, 121*scale, 396*scale), fill=skin, width=max(1,int(22*scale)))
    draw.line((323*scale, 331*scale, 397*scale, 392*scale), fill=skin, width=max(1,int(22*scale)))
    # central map/card
    parchment = (242, 204, 137)
    draw.polygon([(125*scale, 348*scale), (388*scale, 337*scale), (405*scale, 437*scale), (108*scale, 445*scale)], fill=parchment, outline=(139,84,40))
    draw.line((160*scale, 384*scale, 206*scale, 365*scale, 255*scale, 403*scale, 304*scale, 371*scale, 358*scale, 414*scale), fill=(132,84,47), width=max(1,int(3*scale)))
    draw.line((252*scale, 402*scale, 280*scale, 433*scale), fill=(178,53,38), width=max(1,int(7*scale)))
    draw.line((280*scale, 402*scale, 252*scale, 433*scale), fill=(178,53,38), width=max(1,int(7*scale)))


def _theme_object(draw, size, cfg, key):
    s = size / 512
    main, accent = _hex(cfg["main"]), _hex(cfg["accent"])
    if key == "detective":
        _ellipse(draw, (34*s, 295*s, 126*s, 387*s), None, outline=(70,51,40), width=max(2,int(12*s)))
        draw.line((111*s, 370*s, 155*s, 416*s), fill=(70,51,40), width=max(2,int(14*s)))
        for x,y in [(49,445),(79,462),(108,447)]: _ellipse(draw, ((x-10)*s,(y-13)*s,(x+10)*s,(y+13)*s), main)
    elif key == "dino":
        _ellipse(draw, (350*s, 252*s, 492*s, 402*s), main)
        _ellipse(draw, (423*s, 213*s, 500*s, 292*s), main)
        draw.polygon([(364*s,261*s),(380*s,226*s),(394*s,265*s),(410*s,224*s),(424*s,272*s)], fill=accent)
        _ellipse(draw, (468*s, 235*s, 479*s, 246*s), (255,255,255))
        _ellipse(draw, (472*s, 238*s, 477*s, 243*s), (30,30,30))
    elif key == "space":
        draw.polygon([(392*s, 224*s),(469*s, 352*s),(394*s, 332*s),(352*s, 370*s),(360*s, 286*s)], fill=(238,244,250), outline=(82,104,140))
        _ellipse(draw, (389*s, 269*s, 425*s, 305*s), (74,157,220), outline=(40,82,132), width=max(1,int(3*s)))
        draw.polygon([(355*s,333*s),(330*s,390*s),(380*s,355*s)], fill=(241,87,51))
        _ellipse(draw, (42*s, 49*s, 137*s, 144*s), accent)
    elif key == "magic":
        draw.line((376*s, 268*s, 456*s, 189*s), fill=(96,56,39), width=max(2,int(10*s)))
        _spark(draw, 461*s, 184*s, 24*s, accent)
        for x,y,r in [(403,142,8),(452,128,6),(480,232,7),(364,183,6)]: _spark(draw,x*s,y*s,r*s,main)
    elif key == "animal":
        # friendly dog
        _ellipse(draw,(350*s,275*s,488*s,430*s),(196,132,70))
        _ellipse(draw,(372*s,248*s,472*s,354*s),(224,169,105))
        draw.polygon([(374*s,278*s),(344*s,231*s),(401*s,258*s)],fill=(139,87,48))
        draw.polygon([(451*s,258*s),(490*s,227*s),(472*s,291*s)],fill=(139,87,48))
        _ellipse(draw,(394*s,286*s,407*s,299*s),(30,30,30)); _ellipse(draw,(440*s,286*s,453*s,299*s),(30,30,30))
        _ellipse(draw,(418*s,309*s,431*s,321*s),(55,43,35))
    else:
        # compass + mountains
        draw.polygon([(336*s,330*s),(390*s,246*s),(427*s,311*s),(459*s,262*s),(508*s,348*s)],fill=(80,126,96))
        _ellipse(draw,(360*s,357*s,474*s,471*s),(235,216,167),outline=(105,76,45),width=max(2,int(7*s)))
        _ellipse(draw,(376*s,373*s,458*s,455*s),(247,241,214),outline=(105,76,45),width=max(1,int(4*s)))
        draw.polygon([(417*s,385*s),(432*s,423*s),(417*s,414*s),(402*s,423*s)],fill=(186,58,42))


def render_theme_art(theme, size=512):
    key = _theme_key(theme)
    cfg = THEMES[key]
    scale = 2
    work = size * scale
    img = Image.new("RGB", (work, work), (255, 249, 236))
    draw = ImageDraw.Draw(img)
    cfg2 = dict(cfg)
    _background(draw, work, cfg2, key)
    _draw_child(draw, work, cfg2, key)
    _theme_object(draw, work, cfg2, key)
    # warm storybook border
    border = _hex("#8E4F20")
    draw.rounded_rectangle((8*scale,8*scale,work-8*scale,work-8*scale), radius=26*scale, outline=border, width=5*scale)
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _patch_pdf_art():
    import premium_pdf as pdf
    if getattr(pdf, "_illustrated_theme_patch", False):
        return
    pdf._illustrated_theme_patch = True

    old_cover = pdf.CoverArt.draw
    old_child = pdf.ChildCardArt.draw
    old_cert = pdf.CertificateArt.draw

    def cover_draw(self):
        old_cover(self)
        art = render_theme_art(self.t.get("key", "research"), 420)
        self.canv.drawImage(ImageReader(io.BytesIO(art)), self.width-71*mm, self.height-133*mm, 50*mm, 50*mm, preserveAspectRatio=True, anchor="c", mask="auto")

    def child_draw(self):
        old_child(self)
        art = render_theme_art(self.t.get("key", "research"), 300)
        self.canv.drawImage(ImageReader(io.BytesIO(art)), self.width-38*mm, self.height-40*mm, 26*mm, 26*mm, preserveAspectRatio=True, anchor="c", mask="auto")

    def cert_draw(self):
        old_cert(self)
        art = render_theme_art(self.t.get("key", "research"), 300)
        self.canv.drawImage(ImageReader(io.BytesIO(art)), self.width/2-14*mm, self.height-59*mm, 28*mm, 28*mm, preserveAspectRatio=True, anchor="c", mask="auto")

    pdf.CoverArt.draw = cover_draw
    pdf.ChildCardArt.draw = child_draw
    pdf.CertificateArt.draw = cert_draw


def install(legacy):
    _patch_pdf_art()

    @legacy.app.get("/theme-art/<theme>.png")
    def theme_art(theme):
        key = _theme_key(theme)
        if key not in THEMES:
            return Response(status=404)
        response = Response(render_theme_art(key, 512), mimetype="image/png")
        response.headers["Cache-Control"] = "public, max-age=86400"
        return response
