"""Pixel regressions against the exposed ink and warning-rim flanks in source pixels.

Run with Pillow and NumPy: python tests/circuit_detector_pixels.py
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageColor

PUBLIC = Path(__file__).resolve().parents[1] / "web/public/circuits"
CATALOG = json.loads((PUBLIC.parents[2] / "assets/game-circuits/annotations.json").read_text())


def straight_error(original, repaired, item):
    """Select a major axis from exposed source pixels and measure its hidden interval."""
    x, y = item["leader"][0]
    target = np.array(ImageColor.getrgb(item["color"]))
    # Each minor-axis scan must cross exactly one uninterrupted stripe. Reject
    # ambiguous branches and corners on the evidence of the source alone.
    f = np.arange(-23, 24)
    samples = original[y-23:y+24, x-23:x+24]
    visible = np.linalg.norm(samples[:,:,:3]-target,axis=-1) < 55
    yy, xx = np.where(visible & (np.hypot(f[:,None],f)>12))
    columns = xx.std() >= yy.std()

    def measure(image):
        rgb = image[y-23:y+24,x-23:x+24,:3]
        red, green, blue = rgb.transpose(2,0,1)
        signal = (blue-red if target.argmax()==2 else
                  np.minimum(red,green)-blue if target[1]>100 else red-green)
        if not columns:
            signal = signal.T
        # Remove compression noise and attenuate the fringe of nearby symbols.
        mass = np.maximum(0, signal-25)
        mass[np.abs(f) > 18] = 0
        return (f@mass)/np.maximum(1,mass.sum(axis=0)), mass.sum(axis=0)
    centers, strength = measure(original)
    flanks = (abs(f)>=13)&(abs(f)<=21)
    if strength[flanks].min()<320 or strength[flanks].max()>1.45*strength[flanks].min():
        return None
    line = np.polyfit(f[flanks],centers[flanks],1)
    residual = centers[flanks]-np.polyval(line,f[flanks])
    if abs(residual).max()>.38:
        return None
    middle = abs(f)<=9
    actual, strength = measure(repaired)
    assert min(strength[middle])>250, item
    error = abs(actual[middle]-np.polyval(line,f[middle]))/np.hypot(1,line[0])
    return error.max()


def rim_errors(mask, white, item):
    """Measure across every leader segment, including crossings on parallel roads."""
    for p,q in zip(item["leader"], item["leader"][1:]):
        vertical = p[0]==q[0]
        raster = mask.T if vertical else mask
        surface = white.T if vertical else white
        a,b = (p[::-1],q[::-1]) if vertical else (p,q)
        lo,hi = sorted((a[0],b[0]))
        y = a[1]
        def runs(row):
            hits = np.flatnonzero(row>90)
            return [g for g in np.split(hits,np.where(np.diff(hits)>1)[0]+1)
                    if 1<len(g)<15 and lo-15<g.mean()<hi+15]
        above,below = raster[y-4],raster[y+4]
        lower = runs(below)
        for top in runs(above):
            if not lower:
                continue
            bottom = min(lower,key=lambda g: abs(g.mean()-top.mean()))
            a0,a1 = [np.average(g,weights=row[g]) for g,row in ((top,above),(bottom,below))]
            if abs(a1-a0)>15 or not lo+1<(a0+a1)/2<hi-1:
                continue
            values, white_values = [], []
            for dy in range(-3,4):
                t=(dy+4)/8
                expected = (1-t)*a0+t*a1
                half = round(((1-t)*len(top)+t*len(bottom))/2)+2
                ix=np.arange(round(expected)-half,round(expected)+half+1)
                w=raster[y+dy,ix]
                assert w.max()>95, (p,q)
                values.append(abs(np.average(ix,weights=w)-expected))
                brightness = np.maximum(surface[y+dy,ix]-30,0)
                assert brightness.max()>90,(p,q)
                white_values.append(abs(np.average(ix,weights=brightness)-expected))
            yield max(values),max(white_values)


def run(map_dir=PUBLIC/"timing", rim_dir=PUBLIC/"flag-edges"):
    roads, rims, whites = {}, {}, {}
    for slug, info in CATALOG.items():
        original = np.array(Image.open(PUBLIC/"2026"/(slug+".webp")).convert("RGB"),dtype=float)
        rgba = np.array(Image.open(map_dir/(slug+".webp")).convert("RGBA"),dtype=float)
        repaired = rgba[:,:,:3]
        white = repaired.min(axis=2)*rgba[:,:,3]/255
        mask = np.array(Image.open(rim_dir/(slug+".png")).getchannel("A"),dtype=float)
        for i,item in enumerate(info["callouts"],1):
            x,y=item["leader"][0]
            crop=repaired[y-11:y+12,x-11:x+12]
            ink=np.array(ImageColor.getrgb(item["color"]))
            yy,xx=np.mgrid[-11:12,-11:12]
            matches=(np.linalg.norm(crop-ink,axis=-1)<65)
            for radius in (5,8,10):
                ring=abs(np.hypot(xx,yy)-radius)<.7
                assert (matches & ring).sum()>=3, (slug,i,radius)
            error = straight_error(original,repaired,item)
            if error is not None:
                roads[slug,i] = error
            for j,(rim,surface) in enumerate(rim_errors(mask,white,item)):
                rims[slug,i,j] = rim
                whites[slug,i,j] = surface
    return roads,rims,whites


if __name__ == "__main__":
    roads,rims,whites = run()
    print(f"{len(roads)} straight sites: max {max(roads.values()):.3f} px")
    print(f"{len(rims)} rim crossings: max {max(rims.values()):.3f} px")
    print(f"{len(whites)} white crossings: max {max(whites.values()):.3f} px")
    assert len(roads)==24 and len(rims)==67
    assert max(roads.values())<.25 and max(rims.values())<.45 and max(whites.values())<.6

