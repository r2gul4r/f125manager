import {useEffect,useRef} from 'react';
import type {Car} from './timing';
import {teamBadgeStyle} from './teamBadgeStyle';

// Build the trace in distance order from positions actually seen during this session.
export function WorldMap({cars,selected}:{cars:Car[];selected:string}) {
  const trace=useRef(new Map<number,[number,number]>());
  useEffect(()=>{
    for (const car of cars) {
      if (car.world && car.phase!=null && !car.pit && !car.retired)
        trace.current.set(Math.floor(car.phase*240),car.world);
    }
  },[cars]);
  const visible=cars.filter(c=>c.world);
  const points=[...trace.current.values(),...visible.flatMap(c=>c.world?[c.world]:[])];
  if (!points.length) return <section className="circuit panel">Waiting for motion data</section>;
  const xs=points.map(p=>p[0]), zs=points.map(p=>p[1]);
  const left=Math.min(...xs),bottom=Math.min(...zs);
  const width=Math.max(...xs)-left,height=Math.max(...zs)-bottom;
  const scale=Math.min(1150/Math.max(100,width),600/Math.max(100,height));
  const xy=([x,z]:[number,number])=>[626+(x-left-width/2)*scale,352-(z-bottom-height/2)*scale];
  let previous=-2;
  const path=[...trace.current.entries()].sort(([a],[b])=>a-b).map(([bin,p])=>{
    const command=bin-previous===1?'L':'M';
    previous=bin;
    return command+xy(p).join(' ');
  }).join(' ');
  return <section className="circuit panel" aria-label="Live track positions">
    <svg viewBox="0 0 1252 704" role="img" aria-label="Game world coordinates">
      <path d={path} fill="none" stroke="#82828b" strokeWidth="5"/>
      {visible.map(c=><g key={c.code} data-marker={c.code} transform={'translate('+xy(c.world!).join(' ')+')'} style={teamBadgeStyle(c.color,c.retired)}>
        <title>P{c.position} {c.code}</title><circle r="19" fill="var(--team)" stroke={c.code===selected?'white':'#16171b'}/>
        <text textAnchor="middle" dominantBaseline="central" className="map-code">{c.code}</text>
      </g>)}
    </svg></section>;
}

