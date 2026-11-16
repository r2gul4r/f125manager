"""Prepare light or legacy F1 diagrams for the dark live-timing screen."""
from math import hypot

from PIL import Image, ImageDraw, ImageFont


SIZE = (1252, 704)
SCALE = 4
# Full stroke diameters in the 1252×704 source image. Suzuka's two white
# rims measure 2.74 px at half height and sit 34 px apart, centre to centre.
OUTSIDE = 36.75
INSIDE = 31.25
SECTOR_INK = ("#e21071", "#ffd300", "#499fd8")
# Sector boundaries are samples of the registered 480-point lap. Corner badge
# anchors follow the source artwork, in the indicated coordinate space.
LAYOUTS = {
    "bahrain": (158, 355, 1252, [(129,665),(232,587),(142,500),(242,19),(395,212),(501,213),
        (441,309),(645,453),(330,397),(254,493),(890,447),(653,304),(744,68),(1129,619),(1034,687)]),
    "imola": (175, 330, 800, [(479,94),(204,81),(221,119),(149,131),(86,307),(123,337),
        (17,431),(185,428),(278,429),(318,354),(270,269),(308,213),(331,251),(512,213),
        (518,254),(715,119),(784,73),(749,12),(616,89)]),
    "jeddah": (165, 325, 800, [(486,205),(487,221),(459,221),(375,267),(362,299),(327,299),
        (290,325),(278,341),(257,349),(233,331),(203,337),(177,337),(63,414),(135,395),
        (187,393),(211,387),(237,404),(277,397),(337,349),(383,315),(439,257),(516,245),
        (529,220),(552,204),(626,180),(711,113),(737,38)]),
    "lusail": (172, 315, 1252, [(218,650),(424,508),(245,438),(150,146),(297,81),(390,318),
        (473,13),(510,164),(630,211),(570,395),(718,365),(843,54),(998,47),(1085,197),
        (895,383),(1104,668)]),
    "yas-marina": (115, 329, 1252, [(548,585),(748,580),(797,403),(939,520),(1221,487),
        (500,68),(462,111),(362,211),(55,603),(192,403),(246,367),(336,295),(302,424),
        (420,447),(448,237),(532,217)]),
}
LEGACY_FINISH = {
    # x, y, half-width, half-height and vertical clearance for the wider road
    "imola": (912,147,16,15,0), "jeddah": (959,196,16,15,0),
    "lusail": (685,664,13,10,-12), "yas-marina": (599,271,13,20,0),
}


def road_curve(path):
    """Smooth diagram registration noise while preserving the lap/sector indices."""
    count = len(path)
    # Local quadratic fit retains curvature through hairpins. Limit how far a
    # measured point can move, then interpolate the bends between samples.
    points = []
    weights = (-2, 3, 6, 7, 6, 3, -2)
    for index, (x,y) in enumerate(path):
        neighbors = [path[(index+j-3)%count] for j in range(7)]
        dx,dy = (sum(w*p[axis] for w,p in zip(weights,neighbors))/21 - center
                 for axis,center in enumerate((x,y)))
        limit = max(1, hypot(dx,dy) / 2)
        points.append((x+dx/limit, y+dy/limit))
    result = []
    for i in range(count):
        a,b,c,d = (points[(i+j)%count] for j in (-1,0,1,2))
        # Convert the two shared tangents to cubic Bezier control points.
        left = tuple(b[k] + (c[k]-a[k])/6 for k in (0,1))
        right = tuple(c[k] - (d[k]-b[k])/6 for k in (0,1))
        for t in (0,.25,.5,.75):
            u = 1-t
            point = tuple(u**3*b[k] + 3*u*u*t*left[k] + 3*u*t*t*right[k] + t**3*c[k]
                          for k in (0,1))
            result.append(tuple(round(coord*SCALE) for coord in point))
    return result


def render(slug, source, path, public):
    end1, end2, ref_width, corners = LAYOUTS[slug]
    original = Image.open(source).convert("RGBA").resize(SIZE, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", tuple(v*SCALE for v in SIZE))
    ink = ImageDraw.Draw(canvas)
    road = road_curve(path)
    closed = road + road[:1]
    # Same cross-section as Suzuka, in the common diagram viewBox.
    for width, color in [(OUTSIDE, "#f6f6f6"), (INSIDE, "#09090b"), (28, "#15151e")]:
        ink.line(closed, fill=color, width=round(width*SCALE), joint="curve")
    segments = (closed[:4*end1+1], closed[4*end1:4*end2+1], closed[4*end2:])
    for segment, color in zip(segments, SECTOR_INK):
        ink.line(segment, fill=color, width=round(5.5*SCALE), joint="curve")
    canvas = canvas.resize(SIZE, Image.Resampling.LANCZOS)
    for number, (x,y) in enumerate(corners, 1):
        if slug == "bahrain":
            # The light artwork already has the circled turn numbers. Retain
            # their lettering and discard the surrounding white background.
            badge = original.crop((x-12,y-12,x+13,y+13)).resize((21,21),Image.Resampling.LANCZOS)
            mask = Image.new("L",(63,63))
            ImageDraw.Draw(mask).ellipse((0,0,62,62),fill=255)
            canvas.paste(badge,(x-10,y-10),mask.resize((21,21),Image.Resampling.LANCZOS))
        else:
            x,y = (round(v*SIZE[0]/ref_width) for v in (x,y))
            badge = Image.new("RGBA",(63,63))
            draw = ImageDraw.Draw(badge)
            draw.ellipse((0,0,62,62),fill="#f2f2f2")
            draw.text((31,31),str(number),fill="#15151e",anchor="mm",font=ImageFont.load_default(size=39))
            canvas.alpha_composite(badge.resize((21,21),Image.Resampling.LANCZOS),(x-10,y-10))
    if slug == "bahrain":
        # Preserve the original straight-mode hatching and lettering, and
        # the checkered finish crossing that anchors UDP lap distance zero.
        red = Image.new("L", SIZE)
        pixels = original.get_flattened_data() if hasattr(original,"get_flattened_data") else original.getdata()
        red.putdata([min(255,2*(r-max(g,b))) if r-max(g,b)>30 else 0 for r,g,b,_ in pixels])
        canvas.paste("#e10600",(0,0,*SIZE),red)
        finish = (755,640,770,670)
        canvas.paste(original.crop(finish), finish[:2])
    else:
        # The legacy artwork puts its finish flag beside the main straight.
        x,y,w,h,dy = LEGACY_FINISH[slug]
        canvas.alpha_composite(original.crop((x-w,y-h,x+w,y+h)), (x-w,y-h+dy))
    folder = public / "timing"
    folder.mkdir(exist_ok=True)
    canvas.save(folder / (slug+".webp"), lossless=True)

    # Encode the two visible road edges per sector for the shared FlagEdges filter.
    edges = Image.new("RGBA", tuple(v*SCALE for v in SIZE))
    draw = ImageDraw.Draw(edges)
    for segment, color in zip(segments, ("red","lime","blue")):
        draw.line(segment, fill=color, width=round(OUTSIDE*SCALE), joint="curve")
    draw.line(closed, fill=(0,0,0,0), width=round(INSIDE*SCALE), joint="curve")
    edges.resize(SIZE, Image.Resampling.LANCZOS).save(public / "flag-edges" / (slug+".png"))
