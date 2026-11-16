"""Remove printed timing annotations from the detailed maps in source pixel space.

Run from any directory with Pillow and NumPy. The raw WebP and the registered lap
remain the references. Only the callouts, leader lines and sector labels are edited.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageColor, ImageDraw

BASE = Path(__file__).resolve().parent
PUBLIC = BASE.parents[1] / "web/public/circuits"
SCALE = 4


def remove_leader(canvas, start, end):
    """Interpolate across a thin leader, retaining the underlying rim and hatching."""
    x, y = start
    u, v = end
    if x == u:
        remove_leader(canvas.transpose(1, 0, 2), (y, x), (v, u))
        return
    assert y == v
    lo, hi = sorted((x, u))
    cols = np.arange(lo - 2, hi + 3)
    # Work in premultiplied alpha: transparent source pixels may carry arbitrary RGB.
    above, below = canvas[y-3].copy(), canvas[y+3].copy()
    shifts = np.arange(-9, 10)
    costs = []
    for shift in shifts:
        diff = np.abs(above[cols-shift] - below[cols+shift]).sum(axis=1)
        costs.append(np.convolve(np.pad(diff,8,mode="edge"), np.ones(17)/17, mode="valid") + abs(shift)*2)
    best = shifts[np.argmin(costs, axis=0)]
    for dy in range(-2, 3):
        t = (dy+3)/6
        left = cols-np.rint(2*t*best).astype(int)
        right = cols+np.rint(2*(1-t)*best).astype(int)
        current = canvas[y+dy, cols]
        # Keep surviving white rims and saturated ink on either side of the grey wire.
        keep = (current[:,:3].min(axis=1)>170) | (np.ptp(current[:,:3],axis=1)>90)
        canvas[y+dy, cols] = np.where(keep[:,None],current,(1-t)*above[left]+t*below[right])


def restore_rim_crossings(canvas, rim, start, end):
    """Transport the two intact cross-sections over the printed wire."""
    x,y = start
    u,v = end
    if x == u:
        return restore_rim_crossings(canvas.swapaxes(0,1),rim.swapaxes(0,1),(y,x),(v,u))
    lo,hi = sorted((x,u))
    # Work between intact rows. The artwork's nominal leader coordinate can be
    # off by two pixels (Las Vegas). Four pixels clears the full printed wire.
    radius = 4
    above,below = rim[y-radius],rim[y+radius]
    def runs(row):
        hits = np.flatnonzero(row[:,3]>64)
        return [g for g in np.split(hits,np.where(np.diff(hits)>1)[0]+1)
                if 1<len(g)<22 and lo-12<g.mean()<hi+12]
    lower = runs(below)
    for upper in runs(above):
        if not lower:
            break
        def centroid(row,g):
            return np.average(g,weights=row[g,3])
        a = centroid(above,upper)
        partner = min(lower,key=lambda g: abs(centroid(below,g)-a))
        b = centroid(below,partner)
        if abs(b-a)>16 or not lo-3<=(a+b)/2<=hi+3:
            continue
        lower = [g for g in lower if g is not partner]
        for dy in range(1-radius,radius):
            t = (dy+radius)/(2*radius)
            shift = (b-a)*t
            left = int(np.floor(min(upper[0]+shift,partner[0]+shift-(b-a))))-3
            right = int(np.ceil(max(upper[-1]+shift,partner[-1]+shift-(b-a))))+4
            cols = np.arange(max(left,lo-2),min(right,hi+3))
            # Align before blending so a diagonal rim retains its original width.
            for layer in (rim,canvas):
                def profile(row,coords):
                    first = np.floor(coords).astype(int)
                    frac = (coords-first)[:,None]
                    return row[first]*(1-frac)+row[first+1]*frac
                layer[y+dy,cols] = ((1-t)*profile(layer[y-radius],cols-shift)
                                     + t*profile(layer[y+radius],cols+(b-a)-shift))


def sector_curve(path, center, radius, pixel_data, color):
    """Anchor both ends to visible sector ink on the approach and exit."""
    nearest = np.argmin(np.linalg.norm(path-center, axis=1))
    local = path[(np.arange(nearest-28, nearest+29)) % len(path)]
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(local, axis=0), axis=1))]
    t = np.arange(0, arc[-1], .5)
    line = np.column_stack([np.interp(t, arc, local[:,axis]) for axis in (0,1)])
    tangent = np.gradient(line, axis=0)
    normal = np.column_stack([-tangent[:,1],tangent[:,0]])
    normal /= np.linalg.norm(normal,axis=1)[:,None]
    offsets = np.arange(-8,8.1,.5)
    samples = np.rint(line[:,None,:]+normal[:,None,:]*offsets[None,:,None]).astype(int)
    height, width = pixel_data.shape[:2]
    rgb = pixel_data[samples[:,:,1].clip(0,height-1),samples[:,:,0].clip(0,width-1),:3]
    match = np.linalg.norm(rgb - color,axis=2)<65
    count = match.sum(axis=1)
    inside = np.linalg.norm(line-center,axis=1)<radius
    # Use only the contiguous pass through the annotation (parallel roads can be close).
    groups = np.split(np.flatnonzero(inside),np.flatnonzero(np.diff(np.flatnonzero(inside))>1)+1)
    group = min((g for g in groups if len(g)), key=lambda g: np.min(abs(t[g]-arc[28])))
    a,b = group[0],group[-1]
    valid = (count>=5) & (count<=18)
    anchor = np.where(valid)[0]
    if not (np.any(anchor<a) and np.any(anchor>b)):
        raise ValueError(f"Missing sector ink at {center}")
    middle = (match*offsets).sum(axis=1)/np.maximum(1,count)
    # A covered portion has no usable normal measurements. Interpolate between
    # its two source tangents, avoiding errors in the sampled lap under a label.
    before = anchor[(t[anchor]<t[a]) & (t[anchor]>t[a]-12)]
    after = anchor[(t[anchor]>t[b]) & (t[anchor]<t[b]+12)]
    correction = np.interp(t,t[anchor],middle[anchor])
    line += normal*np.convolve(correction,np.ones(11)/11,mode="same")[:,None]
    if len(before)>=6 and len(after)>=6:
        left,right = before[-1],after[0]
        start,end = line[left],line[right]
        span = t[right]-t[left]
        u = ((t[left:right+1]-t[left])/span)[:,None]
        entry = np.polyfit(t[before],line[before],1)[0]
        exit_dir = np.polyfit(t[after],line[after],1)[0]
        line[left:right+1] = ((1+2*u)*(1-u)**2*start + u*(1-u)**2*span*entry
                              + u*u*(3-2*u)*end + u*u*(u-1)*span*exit_dir)
    ends = anchor[(t[anchor]>=t[a]-12)&(t[anchor]<=t[b]+12)]
    # Recover the local ink colour from the actual line outside the hidden portion.
    ink = np.median(rgb[ends][match[ends]],axis=0) if len(ends) else color
    return line[max(0,a-25):b+26],tuple(np.rint(ink).astype(int))


def restore_detectors(image, original, items):
    """Measure the visible ink on parallel cross-sections outside each symbol."""
    centers = np.asarray([item["leader"][0] for item in items], dtype=float)
    origin = centers.mean(axis=0)
    color = np.array(ImageColor.getrgb(items[0]["color"]))
    background = np.array([21, 21, 30])
    left, top = np.floor(centers.min(axis=0)-25).astype(int)
    right, bottom = np.ceil(centers.max(axis=0)+26).astype(int)
    rgb = original[top:bottom, left:right, :3]
    y, x = np.mgrid[top:bottom, left:right]
    xy = np.stack((x,y), axis=-1)
    distance = np.min([np.linalg.norm(xy-c, axis=-1) for c in centers], axis=0)
    ink = (np.linalg.norm(rgb-color,axis=-1)<65) & (distance>11) & (distance<22)
    # Orient the cross-sections along the two visible arms, including steep turns.
    if "bend" in items[0]:
        # For a tight bend or adjacent symbols, use surveyed control points
        # anchored to exposed tangents on the source artwork.
        controls = np.asarray(items[0]["bend"])
        t = np.linspace(0,1,151)[:,None]
        a,b,c,d = controls
        curve = (1-t)**3*a+3*t*(1-t)**2*b+3*t*t*(1-t)*c+t**3*d
        dist_to_line = np.min([np.linalg.norm(xy-p,axis=-1) for p in curve],axis=0)
        paint_detector(image,left,top,rgb,ink,distance,dist_to_line,5.65)
        return
    axis = np.linalg.eigh(np.cov(xy[ink].T))[1][:,-1]
    normal = np.array([-axis[1],axis[0]])
    offset = xy-origin
    along, across = offset@axis, offset@normal
    # Sample in pixel-centre coordinates. Never use the registered vehicle path
    # to infer a tangent from inside the printed icon.
    sites = (centers-origin)@axis
    stations = np.arange(np.floor(sites.min())-20, np.ceil(sites.max())+21)
    v = np.arange(-21,21.01,.125)
    samples = origin + stations[:,None,None]*axis + v[None,:,None]*normal
    base = np.floor(samples).astype(int)
    fx, fy = np.moveaxis(samples-base,-1,0)
    sx, sy = np.moveaxis(base,-1,0)
    values = sum(original[sy+j,sx+i,:3]*weight[:,:,None] for i,j,weight in (
        (0,0,(1-fx)*(1-fy)), (1,0,fx*(1-fy)), (0,1,(1-fx)*fy), (1,1,fx*fy)))
    # Use the strongest colour difference. Neutral rim and leader pixels then
    # have zero ink weight, including the transparent part of the source WebP.
    high, low = np.argmax(color-background), np.argmin(color-background)
    signal = values[:,:,high]-values[:,:,low]
    amplitude = np.median(rgb[ink,high]-rgb[ink,low])
    rows = []
    for u, row, coords in zip(stations,signal,samples):
        indices = np.flatnonzero(row > amplitude*.5)
        pieces = np.split(indices, np.where(np.diff(indices)>1)[0]+1)
        runs = [g for g in pieces if len(g)>23 and len(g)<125 and g[0]>0 and g[-1]+1<len(v)]
        if not runs:
            continue
        run = min(runs, key=lambda g: abs(v[g].mean()))
        if any(np.min(np.linalg.norm(coords[run]-c,axis=1)) < 11.4 for c in centers):
            continue
        i,j = run[0],run[-1]
        inner = v[i-1]+.125*(.5*amplitude-row[i-1])/(row[i]-row[i-1])
        outer = v[j]+.125*(row[j]-.5*amplitude)/(row[j]-row[j+1])
        rows.append((u,(inner+outer)/2,outer-inner))
    u, mid, width = np.array(rows).T
    if not (u[0]<sites.min()-5 and u[-1]>sites.max()+5):
        raise ValueError(f"Missing visible detector flanks at {centers.tolist()}")

    # Fit a straight only when both exposed approaches support it. Otherwise
    # bridge each covered interval using the slopes of its neighbouring ink.
    fit = np.polyfit(u,mid,1)
    if max(abs(mid-np.polyval(fit,u))) <= .32:
        centerline = np.polyval(fit,along)
        slope = np.full_like(along,fit[0])
    else:
        centerline = np.interp(along,u,mid)
        slope = np.interp(along,u,np.gradient(mid,u))
        for i in np.flatnonzero(np.diff(u)>2):
            a,b = u[i:i+2]
            before = (u>=a-6)&(u<=a)
            after = (u>=b)&(u<=b+6)
            if min(before.sum(),after.sum())<2:
                # A short exposed island between two close symbols.
                before = (u>=a-12)&(u<=a)
                after = (u>=b)&(u<=b+12)
            m0 = np.polyfit(u[before]-a,mid[before],1)[0] if before.sum()>1 else (mid[i+1]-mid[i])/(b-a)
            m1 = np.polyfit(u[after]-b,mid[after],1)[0] if after.sum()>1 else (mid[i+1]-mid[i])/(b-a)
            between = (along>=a)&(along<=b)
            t = (along[between]-a)/(b-a)
            secant = (mid[i+1]-mid[i])/(b-a)
            centerline[between] = ((1+2*t)*(1-t)**2*mid[i] + t*t*(3-2*t)*mid[i+1]
                                   + (b-a)*t*(1-t)*(m0*(1-t)-m1*t))
            slope[between] = 6*t*(1-t)*secant + (1-t)*(1-3*t)*m0 + t*(3*t-2)*m1
    # A line of constant physical width occupies more of an oblique scanline.
    thickness = np.median(width/np.hypot(1,np.gradient(mid,u)))
    dist_to_line = abs(across-centerline)/np.hypot(1,slope)
    paint_detector(image,left,top,rgb,ink,distance,dist_to_line,thickness)


def paint_detector(image,left,top,rgb,ink,distance,dist_to_line,thickness):
    background = np.array([21, 21, 30])
    coverage = np.clip(.5+(thickness/2-dist_to_line)/1.3,0,1)
    core = np.median(rgb[ink],axis=0)
    patch = background+(core-background)*coverage[:,:,None]
    blend = np.clip((13-distance)/2,0,1)
    rgba = np.dstack((patch,np.full(distance.shape,255))).round().astype("uint8")
    image.paste(Image.fromarray(rgba),(left,top),Image.fromarray((255*blend).round().astype("uint8")))


def restore_surface(image, original, path, points, color):
    xy = np.array(points)
    center = xy.mean(axis=0)
    radius = np.linalg.norm(xy-center,axis=1).max()+2
    lo = np.floor(center-radius-16).astype(int)
    size = int(2*radius+34)
    mask = Image.new("L",(size*SCALE,)*2)
    draw = ImageDraw.Draw(mask)
    polygon = [tuple(p) for p in ((xy-lo)*SCALE).round().astype(int)]
    draw.polygon(polygon,fill=255)
    draw.line(polygon+polygon[:1], fill=255, width=3*SCALE, joint="curve")
    patch = Image.new("RGBA",mask.size,(21,21,30,255))
    reference = np.array(ImageColor.getrgb(color))
    curve, ink = sector_curve(path,center,radius,original,reference)
    draw = ImageDraw.Draw(patch)
    draw.line([tuple(p) for p in ((curve-lo)*SCALE).round().astype(int)],fill=ink,width=round(5.5*SCALE),joint="curve")
    image.paste(patch.resize((size,size),Image.Resampling.LANCZOS),tuple(lo),
                mask.resize((size,size),Image.Resampling.LANCZOS))


def restore_strip(image, reference, strip):
    left,top,right,bottom = strip["bounds"]
    dx,dy = strip["sourceOffset"]
    # Translating by an integer number of pixels retains the raster's antialiasing.
    sample = reference.crop((left+dx,top+dy,right+dx,bottom+dy))
    width,height = sample.size
    y,x = np.ogrid[:height,:width]
    border = np.minimum(np.minimum(x,width-1-x),np.minimum(y,height-1-y))
    blend = Image.fromarray((np.clip(border/3,0,1)*255).round().astype("uint8"))
    image.paste(sample,(left,top),blend)


def restore_straight(image, reference, straight, rim_file):
    restore_strip(image, reference, straight)
    dx,dy = straight["sourceOffset"]
    # The leader also crossed the warning rim. Its donor is outside the edited
    # rectangle, so rebuilding repeatedly always samples the untouched S3 mask.
    with Image.open(rim_file) as rim_source:
        rim = rim_source.convert("RGBA")
    l,t,r,b = straight["rimBounds"]
    rim.paste(rim.crop((l+dx,t+dy,r+dx,b+dy)), (l,t))
    rim.save(rim_file)


def clean(source, destination, points, annotations):
    reference = Image.open(source).convert("RGBA")
    original = np.asarray(reference,dtype=float)
    canvas = original.copy()
    canvas[:,:,:3] *= canvas[:,:,3:4]/255
    rim_file = destination.parent.parent/"flag-edges"/(destination.stem+".png")
    rim = np.array(Image.open(rim_file).convert("RGBA"),dtype=float)
    # Premultiply the sector channels as well, so empty pixels never dilute
    # the sector ID when shifting antialias coverage across a leader.
    rim[:,:,:3] *= rim[:,:,3:4]/255
    for item in annotations["callouts"]:
        for start,end in zip(item["leader"],item["leader"][1:]):
            remove_leader(canvas,start,end)
            if "straight" not in item:
                restore_rim_crossings(canvas,rim,start,end)
        x,y,u,v = item["box"]
        canvas[y:v+1,x:u+1] = 0
    canvas[:,:,:3] *= 255/np.maximum(canvas[:,:,3:4],1)
    rim[:,:,:3] *= 255/np.maximum(rim[:,:,3:4],1e-8)
    Image.fromarray(np.clip(rim.round(),0,255).astype("uint8")).save(rim_file)
    result = Image.fromarray(np.clip(canvas.round(),0,255).astype("uint8"))
    path = np.asarray(points,dtype=float)
    for item in annotations["sectors"]:
        restore_surface(result,original,path,item["box"],item["color"])
    pending = [item for item in annotations["callouts"] if "straight" not in item and "surfaceStrip" not in item]
    while pending:
        item = pending.pop(0)
        center = np.array(item["leader"][0])
        nearby = [other for other in pending if np.linalg.norm(center-other["leader"][0])<30]
        restore_detectors(result,original,[item,*nearby])
        for other in nearby:
            pending.remove(other)
    for item in annotations["callouts"]:
        if "straight" in item:
            # The leader crosses the lower rim too. Repair both raster layers using
            # the same longitudinal offset so the warning follows the visible rim.
            restore_straight(result, reference, item["straight"], rim_file)
        elif "surfaceStrip" in item:
            restore_strip(result,reference,item["surfaceStrip"])
    result.save(destination,lossless=True)


if __name__ == "__main__":
    catalog = json.loads((BASE/"annotations.json").read_text())
    paths = json.loads((BASE.parent/"boxbox/image-paths.json").read_text())
    (PUBLIC/"timing").mkdir(exist_ok=True)
    for slug, annotations in catalog.items():
        clean(PUBLIC/"2026"/(slug+".webp"), PUBLIC/"timing"/(slug+".webp"), paths[slug], annotations)
