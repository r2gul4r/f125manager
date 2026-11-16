import {Fragment, type ReactNode, useState} from 'react';
import {RankDriver} from './RankDriver';
import {LapReference} from './LapReference';
import type {Frame, TyreExit} from './timing';

function estimate(ms:number, samples:number) {
  const basis = samples ? `실측 ${samples}건` : '모델 추정';
  return <span title={basis}>{(ms/1000).toFixed(2)}s</span>;
}

export function ServiceComparison({frame,lap}:{frame:Frame;lap:number}) {
  const offset = lap - (frame.predictionLap ?? frame.lap);
  const losses = frame.forecast?.serviceRejoins?.[offset] ?? (offset===0 ? frame.serviceForecast : null);
  return <table className="outlook-table pit-service" aria-label="Pit service comparison">
    <caption>Pit service <LapReference label="Pit on" lap={lap}/></caption>
    <colgroup/><colgroup/><colgroup/>
    <thead><tr><th scope="col">Service</th><th scope="col" title="트랙에서 계속 달릴 때와 비교한 예상 시간 손실. 정차 시간 포함">Est. pit loss</th><th scope="col">Rejoin</th></tr></thead>
    <tbody>{['Tyres only','Tyres + front wing'].map((label,i)=>{
      const loss = losses?.[i];
      return <tr key={label}><th scope="row">{label}</th>
        <td>{loss ? estimate(loss[1],loss[2]) : '—'}</td><td>{loss ? 'P'+loss[0] : '—'}</td></tr>;
    })}</tbody>
  </table>;
}

export function ExitNeighbour({frame,exit,side}:{frame:Frame;exit?:TyreExit;side:'ahead'|'behind'}) {
  const ahead = side==='ahead';
  const code = ahead ? exit?.before : exit?.after;
  const car = code && frame.cars.find(c=>c.code===code);
  if (!car || !exit) return <>—</>;
  const gap = ahead ? exit.aheadGapMs : exit.behindGapMs;
  return <span className="exit-neighbour"><RankDriver car={car} rank={exit.position+(ahead?-1:1)}/>
    <strong data-trend={ahead?exit.aheadTrend:exit.behindTrend}>{gap==null?'—':(ahead?'+':'−')+(gap/1000).toFixed(3)+'s'}</strong></span>;
}

export function AfterPit({frame,lap,exit}:{frame:Frame;lap:number;exit?:TyreExit}) {
  return <table className="outlook-table after-pit" aria-label="After pit" data-shown-exit={exit ? lap : undefined}>
    <caption>After pit <span className="lap-reference">L{lap} · Tyres only</span></caption>
    <colgroup/><colgroup/><colgroup/>
    <thead><tr><th>Ahead</th><th>My position</th><th>Behind</th></tr></thead>
    <tbody><tr><td><ExitNeighbour frame={frame} exit={exit} side="ahead"/></td><td>{exit?'P'+exit.position:'—'}</td><td><ExitNeighbour frame={frame} exit={exit} side="behind"/></td></tr></tbody>
  </table>;
}

function TrafficAhead({frame,exit}:{frame:Frame;exit?:TyreExit}) {
  const [expanded,setExpanded] = useState(false);
  if (!exit?.trafficAhead) return <>—</>;
  if (!exit.trafficAhead.length) return <>0 cars</>;
  const entries = exit.trafficAhead.map(([code,ms],index)=>{
    const car = frame.cars.find(c=>c.code===code);
    return <span key={code} className="traffic-car">
      {car ? <RankDriver car={car} rank={exit.position-index-1}/> : <b>{code}</b>}
      <strong>+{(ms/1000).toFixed(3)}s</strong>
    </span>;
  });
  return <div className="traffic-list">
    {entries.slice(0,2)}
    {entries.length>2 && <button type="button" className="traffic-more" aria-expanded={expanded}
      aria-label={`${expanded?'Hide':'Show'} ${entries.length-2} more drivers`} onClick={()=>setExpanded(!expanded)}>
      {expanded?'−':'+'}{entries.length-2}
    </button>}
    {expanded && entries.slice(2)}
  </div>;
}

export function RiskDetails({frame,exit,counts}:{frame:Frame;exit?:TyreExit;counts?:number[]}) {
  const lost = exit && exit.position-exit.entryPosition;
  const windowMs = frame.forecast?.trafficWindowMs;
  const rivals = (frame.forecast?.cutRivals ?? []).flatMap(code=>frame.cars.filter(car=>car.code===code).slice(0,1));
  const cutCell = (side:0|1) => <span className="cut-outcome">
    {rivals.map((car,i)=><Fragment key={car.code}>{i>0 && <span aria-hidden="true">/</span>}<RankDriver car={car} rank={car.position}/></Fragment>)}
    <strong>{counts && counts[2]>0 ? Math.round(100*counts[side]/counts[2])+'%' : '—'}</strong>
  </span>;
  const metrics: {label:string;value:ReactNode;title?:string}[] = [
    {label:'Pit entry → exit',value:exit && lost!=null ? <span className="pit-position-change">
      <span>P{exit.entryPosition} → P{exit.position}</span>{' '}
      <small>{Math.abs(lost)} {lost<0?'gained':'lost'}</small>
    </span>:'—'},
    {label:'Traffic ahead'+(windowMs!=null?' ≤'+windowMs/1000+'s':''),value:<TrafficAhead frame={frame} exit={exit}/>},
    ...(['Undercut by','Overcut by'] as const).map((label,i)=>({label,value:cutCell(i===0?0:1),title:'Share of simulated pit timings where at least one listed rival gets ahead after both first stops.'}))
  ];
  return <table className="outlook-table cut-risk" aria-label="Risk details">
    <caption>Risk details</caption>
    <thead><tr>{metrics.map(({label,title})=><th key={label} scope="col" title={title}>{label}</th>)}</tr></thead>
    <tbody><tr>{metrics.map(({label,value})=><td key={label}>{value}</td>)}</tr></tbody>
  </table>;
}
