import {Fragment, useEffect, useRef} from 'react';
import {pitSchedule} from './raceEditor';
import {TyreBadge} from './TyreBadge';
import {LapReference} from './LapReference';
import {ServiceComparison, AfterPit, ExitNeighbour, RiskDetails} from './PitOutlook';
import {compounds, type Car, type Frame, type ForecastPlan, type TyreExit, type Stop, type Plan} from './timing';
import {formatLapTime, formatSignedDelta} from './vendor/utils/formatters';

const titles = {A:'Balanced', B:'Undercut', C:'Overcut'};
function centralFinish(plan:Omit<ForecastPlan,'id'>) {
  // Rust's five pace scenarios are ordered from -4 to +4, with zero in the middle.
  const rank = plan.scenarioRanks?.[2] ?? (plan.finish[0]===plan.finish[1] ? plan.finish[0] : null);
  return rank==null?'—':'P'+rank;
}

export function PaceHistory({rows,source='Demo'}:{source?:string;rows:NonNullable<Frame['paceHistory']>}) {
  const clean = rows.filter(row=>row[2]==='Clean');
  return <section className="pace-history"><h2>Recent pace <small>{source} · completed laps</small></h2>
    {rows.length ? <><div className="lap-strip">{rows.map(([n,time,state])=><div key={n}><small>L{n} · {state}</small>
      <b>{formatLapTime(time)}</b></div>)}</div>
      {clean.length>1 && <small>Clean lap change · {formatSignedDelta(clean[clean.length-1][1]-clean[0][1])} s</small>}</>
      : <p lang="ko">첫 완료 랩 대기 중</p>}</section>;
}

export function paceWait(frame:Frame, ready:boolean, other?:Car) {
  const me=frame.cars[frame.player];
  if (!ready) return '비교할 랩 없음';
  if (frame.mode==='grid') return '출발 전 · 완료 랩 대기';
  if (me.retired) return '리타이어 · 분석 종료';
  if (!other) return '해당 순위에 상대 차량 없음';
  if (me.pit || other.pit) return '피트 랩 제외 · 정상 랩 대기';
  if (other.retired) return '상대 리타이어';
  if (frame.flag==='RED' || (!frame.source && frame.flag!=='TRACK CLEAR')) return frame.flag+' · 정상 주행 재개 대기';
  return frame.source?'같은 랩의 유효 기록과 차간 격차 수집 중':'유효 랩 대기 · 현재 상대와의 비교 표본 부족';
}

export function StintBar({plan,total=27,fromLap}: {plan:Plan;total?:number;fromLap?:number}) {
  const starts=plan.start || fromLap!=null ? [{lap:fromLap ?? 1,tyre:plan.start},...plan.stops] : plan.stops;
  return <span className="stint-bar" aria-label="Planned tyre stints">{starts.map((s,i)=>{
    const end=(starts[i+1]?.lap ?? total+1)-1;
    if(end<s.lap) return null;
    return <span key={i} data-compound={s.tyre} style={{flexGrow:end-s.lap+1}}
      title={(s.tyre ? compounds[s.tyre] : 'Unknown')+' · L'+s.lap+'–'+end}><TyreBadge compound={s.tyre}/> <small>{s.lap}–{end}</small></span>;
  })}</span>;
}

function StopSequence({stops,count=false}:{stops:Stop[];count?:boolean}) {
  return <span className="stop-sequence">{stops.map((s,i)=><span className="schedule-stop" key={s.lap}>{i>0 && <span className="schedule-arrow">→</span>}<span className="schedule-lap">L{s.lap}</span> <TyreBadge compound={s.tyre}/></span>)}
    {!stops.length && 'Stay out'}{count && <small>{stops.length} {stops.length===1?'stop':'stops'}</small>}</span>;
}

function wearRisk(plan:Omit<ForecastPlan,'id'>, from:number, to:number) {
  const estimate = plan.wearRisk?.[from];
  const life = estimate?.excessPct!=null ? `잔여 수명 ${estimate.excessPct}% 초과` : `수명 ${to-from+1}랩 초과`;
  return <>{estimate?.wearPct!=null && <span className="risk-fact">예상 마모 {estimate.wearPct}%</span>} <span className="risk-fact">{life}</span></>;
}

function PlanRisk({plan,frame}:{plan:Omit<ForecastPlan,'id'>;frame:Frame}) {
  if (!plan.lifeShortfall) return <>{plan.risk}</>;
  if (plan.tyreIssues?.length) return <span className="tyre-risk" lang="ko">{plan.tyreIssues.map(([from,to,tyre,reason])=>
    <span key={from}><span className="risk-fact">L{from}{to>from?'–'+to:''} <TyreBadge compound={tyre}/></span> {reason==='stock'?'세트 없음':reason==='weather'?'노면용 세트 없음':wearRisk(plan,from,to)}</span>)}</span>;
  // Earlier forecasts only carry the total deficit. Attribute it only when the fitted set explains it all.
  const first = plan.stop.lap - plan.lifeShortfall;
  if (!frame.previousPlans && frame.fittedLife!=null && first===frame.lap+frame.fittedLife) {
    return <span className="tyre-risk" lang="ko">L{first}{first<plan.stop.lap-1?'–'+(plan.stop.lap-1):''} <TyreBadge compound={frame.cars[frame.player].tyre}/> · 수명 {plan.lifeShortfall}랩 초과</span>;
  }
  return <span className="tyre-risk" lang="ko">세트 수명 {plan.lifeShortfall}랩 부족 · 구간 미확인</span>;
}

function RejoinForecast({frame,exit,pitLap}:{frame:Frame;exit?:TyreExit;pitLap:number}) {
  if (!exit) return <small lang="ko">피트 복귀 예측 대기 중</small>;
  return <div className="rejoin-forecast" aria-label="Pit exit forecast" data-shown-exit={pitLap}>
    <div className="rejoin-summary"><small>Est. rejoin · L{pitLap}</small><b>P{exit.position}</b></div>
    <div className="rejoin-neighbours">{(['ahead','behind'] as const).map(side=>{
      const label = side==='ahead'?'Ahead':'Behind';
      return <span key={side} aria-label={label}><small>{label}</small><ExitNeighbour frame={frame} exit={exit} side={side}/></span>;
    })}</div>
  </div>;
}

function upcomingStops(frame:Frame) {
  const observed=frame.observedStints ?? [];
  return frame.plan.stops.filter(s=>!observed.some(actual=>actual.lap===s.lap && actual.tyre===s.tyre)
    && !frame.pitComparisons?.some(p=>p.exitMs!=null && p.lap===s.lap && s.tyre===frame.cars[frame.player].tyre));
}

export function SelectedPlan({frame}:{frame:Frame}) {
  const observed=frame.observedStints ?? [];
  const unserved=upcomingStops(frame);
  const next=unserved.find(s=>frame.mode==='grid' || s.lap>=frame.lap);
  const selected=!!frame.selectedPlan || !!frame.plan.stops.length;
  const exit=next && frame.forecast?.tyreExits?.[next.lap-(frame.predictionLap ?? frame.lap)];
  return <section className="weather-call" aria-label="Selected strategy"><small>Selected plan</small><div className="recommended-stops">
    {frame.selectedPlan && <b>Plan {frame.selectedPlan}</b>}
    {next ? <span className="next-compound"><StopSequence stops={[next]}/> {compounds[next.tyre]}</span> : selected ? <span>{unserved.length?'No upcoming stop':'Stay out'} · <TyreBadge compound={frame.cars[frame.player].tyre}/></span> : <span>—</span>}</div>
    {next && <RejoinForecast frame={frame} exit={exit} pitLap={next.lap}/>}
    {observed.length>0 && <small>Last stop · L{observed[observed.length-1].lap} <TyreBadge compound={observed[observed.length-1].tyre}/></small>}
  </section>;
}

function PlanCells({plan,stops}:{plan:Omit<ForecastPlan,'id'>;stops:Stop[]}) {
  const [open,close]=plan.window;
  return <><td><StopSequence stops={stops} count/></td>
    <td><span className="pit-window">{!stops.length?'—':'L'+open+(open!==close?'–'+close:'')}</span></td>
    <td className="finish-range">{centralFinish(plan)}</td><td data-risk={plan.risk.toLowerCase()}>{plan.risk}</td></>;
}

export function StrategyAnalysis({frame,ready,index,select,apply}:{
  frame:Frame;ready:boolean;index:number;select:(n:number)=>void;apply:(n:number)=>void;

}) {

  const hoverTimer=useRef<number | undefined>(undefined);
  const pointerFocus=useRef(false);
  const clearHover=()=>window.clearTimeout(hoverTimer.current);
  useEffect(()=>clearHover,[]);
  const forecast=frame.forecast;
  const strategies=forecast?.plans ?? frame.previousPlans?.plans ?? [];
  const basis=forecast ? frame.predictionLap ?? frame.lap : frame.previousPlans?.lap ?? frame.lap;
  const pitPreview=!forecast && frame.cars[frame.player].pit ? frame.previousPlans : undefined;
  const fromLap=Math.max(1,!forecast && frame.previousPlans ? basis : frame.lap);
  const preview=forecast ?? frame.previousPlans;
  const outlook=forecast ? frame : {...frame,forecast:preview,predictionLap:basis,serviceForecast:null};

  return <section className="plan-comparison" aria-label="Strategy comparison">
    <div className="panel-tools"><h3>Plans {strategies.length && frame.mode!=='grid' ? <LapReference label={forecast?'Forecast from':pitPreview?'Before pit entry':'Last forecast'} lap={basis}/> : <small>{strategies.length?'Pre-race forecast':frame.forecastWait ?? 'Awaiting forecast'}</small>}</h3></div>
    <div className="work-scroll"><table className="plan-table"><thead><tr>{['Plan','Pit schedule','Pit window','Est. finish','Risk'].map(h=><th scope="col" key={h}>{h}</th>)}</tr></thead>
      <tbody>{strategies.map((s,i)=>{
        const expanded = !s.codexExpired && frame.mode==='race' && i===index;
        const stops = pitSchedule(s,frame).filter(stop=>stop.lap>=fromLap);
        const target = stops[0];
        const exit = target && preview?.tyreExits?.[target.lap-basis];
        const hover = () => {if (!s.codexExpired && frame.mode==='race' && i!==index) select(i);};
        return <Fragment key={s.id}><tr className={s.codexExpired?'expired-plan':undefined} data-active={i===index && !s.codexExpired} onPointerEnter={e=>{clearHover(); if(e.pointerType==='mouse') hoverTimer.current=window.setTimeout(hover,140);}}
          onPointerLeave={()=>{clearHover();pointerFocus.current=false;}} onPointerDown={()=>{clearHover();pointerFocus.current=true;}} onPointerUp={()=>{pointerFocus.current=false;}}>
          <td><button className="plan-choice" title={s.codexReason} disabled={s.codexExpired} aria-label={`Plan ${s.id} · ${titles[s.id]}`} aria-pressed={i===index && !s.codexExpired}
            aria-expanded={frame.mode==='race'?expanded:undefined} onFocus={()=>{if(!pointerFocus.current) hover();}} onClick={()=>{clearHover();if(ready && forecast) apply(i); else select(i);}}>{s.id===frame.selectedPlan && <span className="plan-check" aria-label="Selected">✓ </span>}Plan {s.id}
            {!s.codexExpired && s.id===(forecast ?? frame.previousPlans)?.recommended && <span className="plan-rec">Recommended</span>}<small>{titles[s.id]}</small></button></td>
          {s.codexExpired ? <><td><StopSequence stops={s.stops ?? []}/></td><td colSpan={3}><span className="expired-mark" aria-hidden="true">×</span> <span role="status">Expired · Awaiting Codex</span></td></> : <PlanCells plan={s} stops={stops}/>}</tr>
          {expanded && <tr className="plan-preview"><td colSpan={5}><section aria-label={'Plan '+s.id+' preview'}>
            <div className="preview-heading"><strong>Stints</strong></div>
            <StintBar fromLap={fromLap} total={frame.totalLaps} plan={{start:pitPreview?.startTyre ?? frame.cars[frame.player].tyre,stops}}/>
            {target && <><div className="pit-outlooks">
              <ServiceComparison frame={outlook} lap={target.lap}/>
              <AfterPit frame={frame} lap={target.lap} exit={exit}/>
            </div><RiskDetails frame={outlook} exit={exit}
              counts={preview?.cutScenarios?.[target.tyre]?.[target.lap-basis]}/></>}
            {!!s.lifeShortfall && <div className="plan-context"><PlanRisk plan={s} frame={frame}/></div>}
          </section></td></tr>}</Fragment>;
      })}
        {!strategies.length && Object.entries(titles).map(([id,title])=><tr key={id}><td>Plan {id} · {title}</td>{['stop','time','finish','risk'].map(k=><td key={k}>—</td>)}</tr>)}</tbody></table></div>
  </section>;
}
