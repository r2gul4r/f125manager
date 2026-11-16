import {teamBadgeStyle} from './teamBadgeStyle';
import {useEffect, useLayoutEffect, useMemo, useRef, useState} from 'react';
import {trackLayout, type CircuitMap} from './circuits';
import type {Car, Frame} from './timing';
import {indexRim,yellowIntervals} from './marshalZones';

// RGB channels in the edge mask encode S1, S2 and S3; its alpha contains
// the original edge coverage, keeping the centreline and map labels untouched.
function FlagEdges({id, flag, sectors, zoneImage}: {id: string; flag: string; sectors?: number[]; zoneImage?:string}) {
  if (!['YELLOW', 'RED', 'SC', 'VSC'].includes(flag)) return null;
  const local = flag === 'YELLOW' && sectors && sectors.length > 0;
  const channels = [1,2,3].map(n => !local || sectors.includes(n) ? 1 : 0);
  const matrix = `0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  ${channels.join(" ")} 0 0`;
  return <g className="flag-edges" data-flag={flag} data-sectors={zoneImage ? undefined : local ? sectors.join(',') : 'all'}>
    <defs><filter id="edge-ink" x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
      <feColorMatrix type="matrix" values={matrix}/>
      <feComposite in2="SourceGraphic" operator="in"/>
      <feMorphology operator="dilate" radius="2" result="rim"/>
      <feFlood floodColor="var(--signal)"/>
      <feComposite in2="rim" operator="in" result="stroke"/>
      <feGaussianBlur in="stroke" stdDeviation="2" result="glow"/>
      <feMerge><feMergeNode in="glow"/><feMergeNode in="stroke"/></feMerge>
    </filter></defs>
    <image href={zoneImage ?? `/circuits/flag-edges/${id}.png`} width="1252" height="704" filter="url(#edge-ink)"/>
  </g>;
}

function MarshalWarning({venue,zones}: {venue:CircuitMap; zones:NonNullable<Frame['marshalZones']>}) {
  const [rim,setRim]=useState<ReturnType<typeof indexRim>>();
  useEffect(()=>{
    let current=true;
    const image=new Image();
    image.onload=()=>{
      if (!current) return;
      const canvas=document.createElement('canvas');
      canvas.width=image.naturalWidth; canvas.height=image.naturalHeight;
      const ctx=canvas.getContext('2d')!;
      ctx.drawImage(image,0,0);
      const apply=indexRim(ctx.getImageData(0,0,canvas.width,canvas.height),trackLayout(venue).path,!!venue.reverse);
      setRim(()=>apply);
    };
    image.src=`/circuits/flag-edges/${venue.id}.png`;
    return ()=>{current=false;};
  },[venue]);
  // WS snapshots repeat at 10 Hz; redraw only when the yellow intervals change.
  const rangeKey=JSON.stringify(yellowIntervals(zones));
  const url=useMemo(()=>{
    if (!rim || rangeKey==='[]') return;
    const data=rim(JSON.parse(rangeKey));
    const canvas=document.createElement('canvas');
    canvas.width=data.width; canvas.height=data.height;
    canvas.getContext('2d')!.putImageData(data,0,0);
    return canvas.toDataURL();
  },[rim,rangeKey]);
  return url ? <g data-yellow-intervals={rangeKey}><FlagEdges id={venue.id} flag="YELLOW" zoneImage={url}/></g> : null;
}

interface Sample {time: number; phases: Map<string,number>; lap: number}
const renderDelay = 120; // Keep one 10 Hz snapshot in reserve to follow bends and the finish line.

export function Circuit({venue, cars, selected, lap, flag, yellowSectors,marshalZones}: {flag: string; yellowSectors?: number[]; marshalZones?:Frame['marshalZones']; venue: CircuitMap; cars: Car[]; selected: Car; lap: number}) {
  const layout = useMemo(()=>trackLayout(venue), [venue]);
  const {location} = layout;
  const layer = useRef<SVGGElement>(null);
  const history = useRef<Sample[]>([]);
  useLayoutEffect(() => {
    const time = performance.now();
    const previous = history.current.at(-1);
    if (previous && (time-previous.time > 500 || lap < previous.lap)) history.current = [];
    history.current.push({time, lap, phases: new Map(cars.map(car => [car.code, car.phase ?? 0]))});
    history.current = history.current.slice(-5);
  }, [cars, lap]);

  useLayoutEffect(() => {
    let request = 0;
    const interval = 1000 / 60;
    let nextPaint = performance.now();
    function draw(now: number) {
      request = requestAnimationFrame(draw);
      if (now + 0.5 < nextPaint) return;
      nextPaint += Math.max(1, Math.floor((now + 0.5 - nextPaint) / interval) + 1) * interval;
      const samples = history.current;
      const at = now-renderDelay;
      const index = samples.findIndex(sample => sample.time >= at);
      const next = samples[index < 0 ? samples.length-1 : index];
      const prev = index > 0 ? samples[index-1] : next;
      if (layer.current && next) {
        const mix = next === prev ? 1 : (at-prev.time)/(next.time-prev.time);
        for (const node of layer.current.children) {
          const marker = node.firstElementChild!;
          const code = marker.getAttribute('data-marker')!;
          const target = next.phases.get(code);
          if (target === undefined) continue;
          const start = prev.phases.get(code) ?? target;
          const delta = ((target-start+1.5)%1)-.5;
          const phase = (start + delta*mix + 1)%1;
          const p = location(phase);
          const belowBridge = venue.id === 'suzuka' && phase > .423 && phase < .458;
          if (belowBridge !== node.hasAttribute('mask')) {
            if (belowBridge) node.setAttribute('mask', 'url(#suzuka-underpass)');
            else node.removeAttribute('mask');
          }
          const transform = `translate(${p.x.toFixed(2)} ${p.y.toFixed(2)})`;
          if (marker.getAttribute('transform') !== transform) marker.setAttribute('transform', transform);
        }
      }
    }
    draw(performance.now());
    return () => cancelAnimationFrame(request);
  }, [location, venue.id]);

  // The selected car stays visible when cars occupy the same part of the track.
  const ordered = [...cars].sort((a,b) => Number(a.code===selected.code)-Number(b.code===selected.code) || b.position-a.position);
  return <section className="circuit panel" aria-label={venue.officialName+" track map"} data-circuit={venue.id}>
    <svg viewBox="0 0 1252 704" role="img" aria-label={`${venue.officialName} · positions of ${cars.length} drivers`}>
      <defs>
        <mask id="suzuka-underpass" maskUnits="userSpaceOnUse" x="0" y="0" width="1252" height="704">
          <rect width="1252" height="704" fill="white"/>
          <path d="M487 318L557 343" fill="none" stroke="black" strokeWidth="17"/>
        </mask>
      </defs>
      <image className="circuit-art" href={`/circuits/timing/${venue.id}.webp`} width="1252" height="704"/>
      {marshalZones && <MarshalWarning venue={venue} zones={flag==='YELLOW'?marshalZones:[]}/>}
      {(!marshalZones || flag!=='YELLOW') && <FlagEdges id={venue.id} flag={flag} sectors={yellowSectors}/>}
      <g ref={layer}>{ordered.map(car => <g key={car.code}><g style={teamBadgeStyle(car.color, car.retired)} data-marker={car.code} data-selected={car.code===selected.code}>
        <title>P{car.position} {car.code}</title>
        <circle r="19" fill="var(--team)" stroke={car.code===selected.code?'white':'#16171b'} strokeWidth={car.code===selected.code?3:1.5}/>
        <text textAnchor="middle" dominantBaseline="central" className="map-code">{car.code}</text>
      </g></g>)}</g>
    </svg>
  </section>;
}
