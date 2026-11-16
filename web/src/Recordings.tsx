import {useEffect, useRef, useState} from 'react';
import {liveVenue} from './circuits';
import type {PitComparison} from './timing';
import {TelemetryComparison} from './TelemetryComparison';
import {PitReview} from './PitReview';

type Recording = {id:string;sessionName:string;track:number|null;startedMs:number;durationMs:number;stops:PitComparison[];observedStops?:PitComparison[]};
export interface Playback {ms:number;duration:number;speed:number}
const clock=(ms:number)=>Math.floor(ms/60000)+':'+String(Math.floor(ms/1000)%60).padStart(2,'0');

const parts:Record<string,string>={frontLeft:'왼쪽 앞날개',frontRight:'오른쪽 앞날개',rearWing:'리어윙',floor:'바닥',diffuser:'디퓨저',sidepod:'사이드포드'};

function serviceLabel(stop:PitComparison) {
  const work=[];
  if(stop.tyreChanged) work.push('타이어 교체');
  if(stop.wingRepair) work.push('앞날개 수리');
  for(const part of stop.repairs??[]) if(part!=='frontLeft' && part!=='frontRight') work.push((parts[part]??part)+' 손상 감소');
  if(stop.repairs?.length===0) work.push('차체 수리 없음');
  if(stop.actual!=null && stop.tyreChanged==null && 'tyreChanged' in stop) work.push('타이어 교체 미확인');
  if(stop.pitExperience!=null) work.push(['Automatic','Broadcast','Immersive'][stop.pitExperience]??'Unknown');
  if(stop.serviceDelayed) work.push('같은 조건보다 긴 정차 · 지연 의심');
  if(stop.serviceVerdict==='overlap') work.push('정상·지연 범위 겹침');
  if(stop.serviceVerdict==='outsideProfile') work.push('게임 기준 불일치');
  if(stop.actual!=null && stop.serviceIncluded!=null) {
    const phase = stop.safetyChanged && stop.serviceSafety!=null ? (['Green','SC','VSC','Formation','Mixed'][stop.serviceSafety]??'Unknown')+' ' : '';
    work.push(phase+(stop.serviceIncluded?'정차 평균 포함':'정차 평균 제외'));
    if(stop.measuredLossMs!=null) work.push('피트 손실 '+(stop.measuredLossMs/1000).toFixed(2)+'초'+(stop.transitReferences?' · 같은 구간 '+stop.transitReferences+'대 비교':''));
    if(stop.serviceIncluded && !stop.lossIncluded) work.push(stop.safetyChanged?'깃발 전환 · 복귀 손실 평균 제외':'복귀 손실 미측정');
  }
  if(stop.penalty) work.push('페널티');
  if(stop.safety!=null) work.push((stop.safetyStates??[stop.safety]).map(s=>['Green','SC','VSC','Formation'][s]??'Unknown').join(' → '));
  return work.length?' · '+work.join(' · '):'';
}

export function PitResults({stops,heading="Pit rejoin comparison",inPit=false}:{stops:PitComparison[];heading?:string;inPit?:boolean}) {
  const backtest=stops.some(s=>'recalculated' in s);
  const rankCell=(rank:number|null|undefined,actual:number|null)=> <td>{rank==null?'—':'P'+rank}
    {rank!=null && actual!=null && <small lang="ko"> · {rank===actual?'일치':Math.abs(actual-rank)+'자리 '+(actual<rank?'앞':'뒤')}</small>}</td>;
  return <section className="pit-results" aria-label={heading}><h3>{heading}</h3>
    {stops.length ? <table><thead><tr><th>Entry lap</th><th>Recorded forecast</th>{backtest && <th>Replay estimate</th>}<th>Observed exit</th></tr></thead>
      <tbody>{stops.slice().reverse().map(s=><tr key={s.entryMs}><td>L{s.lap}{s.serviceMs ? ' · '+(s.serviceMs/1000).toFixed(1)+' s':''}{serviceLabel(s)}
        {s.entryScenarios && <small style={{display:'block'}}>{backtest?'Replay':'Entry'} · Tyres P{s.entryScenarios[0][0]} / + Wing P{s.entryScenarios[1][0]}</small>}
        {backtest && s.recordedScenarios && <small style={{display:'block'}}>Recorded · Tyres P{s.recordedScenarios[0][0]} / + Wing P{s.recordedScenarios[1][0]}</small>}</td>
        {rankCell(s.predicted,s.actual)}{backtest && rankCell(s.recalculated,s.actual)}
        <td>{s.actual!=null?'P'+s.actual:inPit && s===stops.at(-1)?'복귀 대기':'출구 순위 미기록'}</td></tr>)}</tbody></table>:
      <p lang="ko">기록된 피트 진입 없음</p>}</section>;
}

export function Recordings({initialRecording}:{initialRecording:string|null}){
  const [rows,setRows]=useState<Recording[]>([]);
  const [selected,select]=useState(initialRecording??'');
  const [track,pickTrack]=useState('');
  const [status,setStatus]=useState('Loading…');
  useEffect(()=>{
    const abort=new AbortController();
    let fetching=false;
    async function refresh(){
      if(fetching)return;
      fetching=true;
      try {
        const response=await fetch('/api/recordings',{signal:abort.signal,cache:'no-store'});
        if(!response.ok) throw new Error();
        const data:Recording[]=await response.json();
        setRows(data);setStatus(data.length?'':'게임에서 주행하면 세션이 자동으로 저장됨');
      } catch {if(!abort.signal.aborted)setStatus('녹화 목록을 읽을 수 없음');} finally {fetching=false;}
    }
    void refresh();const timer=setInterval(refresh,3000);
    return ()=>{clearInterval(timer);abort.abort();};
  },[]);
  const filtered=rows.filter(r=>!track || String(r.track)===track);
  const row=filtered.find(r=>r.id===selected);
  return <><h3>Sessions</h3>{status && <p role="status">{status}</p>}
    <div className="panel-tools"><label>Grand Prix <select value={track} onChange={e=>{pickTrack(e.target.value);select(rows.find(r=>String(r.track)===e.target.value)?.id??'');}}>
      <option value="">All circuits</option>{[...new Set(rows.map(r=>r.track))].filter(t=>t!=null).map(t=><option key={t} value={t}>{liveVenue(t)?.officialName??'Track '+t}</option>)}</select></label>
      <label>Session <select aria-label="Recorded session" value={row?.id??''} onChange={e=>select(e.target.value)}>
      <option value="">Current session · Live</option>{filtered.map(r=><option key={r.id} value={r.id}>{new Date(r.startedMs).toLocaleString()} · {liveVenue(r.track??-1)?.officialName??'Track '+(r.track??'—')} · {r.sessionName}</option>)}</select></label>
      {row && <><button onClick={()=>{location.search='?replay='+encodeURIComponent(row.id);}}>Open in My Race</button><span>{clock(row.durationMs)}</span></>}</div>
    {row?.stops.some(s=>s.exitMs!=null) && <PitReview key={row.id} recording={row.id} revision={row.stops.filter(s=>s.exitMs!=null).length}/>}
    <TelemetryComparison key={selected||'live'} recording={selected||'live'}/>{row && <PitResults stops={row.stops}/>}
    {!!row?.observedStops?.length && <><PitResults stops={row.observedStops} heading="Live pit result"/><p lang="ko">원본 녹화가 끊긴 구간에서 실시간 화면으로 확인한 기록</p></>}</>;
}

export function ReplayTools({state,send}:{state:Playback|null;send:(msg:object)=>boolean}){
  const [draft,setDraft] = useState<number|null>(null);
  const dragging = useRef(false);
  const seek = (ms:number) => {
    setDraft(null);
    send({type:'playback',ms,speed:0});
  };
  return <div className="panel-tools replay-tools" aria-label="Replay controls">
    {state && <><button onClick={()=>send({type:'playback',speed:state.speed?0:1,...(state.ms===state.duration?{ms:0}:{})})}>{state.speed?'Pause':'Play'}</button>
      <select aria-label="Playback speed" value={state.speed} onChange={e=>send({type:'playback',speed:+e.target.value})}>
        {[0,1,4,16].map(n=><option key={n} value={n}>{n?n+'×':'Paused'}</option>)}</select>
      <input aria-label="Replay time" type="range" min={0} max={state.duration} step={1} value={draft ?? state.ms}
        onPointerDown={e=>{
          if (!e.isPrimary || e.button!==0) return;
          dragging.current=true;
          e.currentTarget.setPointerCapture(e.pointerId);
          setDraft(e.currentTarget.valueAsNumber);
        }}
        onChange={e=>{if (dragging.current) setDraft(e.target.valueAsNumber); else seek(e.target.valueAsNumber);}}
        onPointerUp={e=>{if (dragging.current && e.isPrimary) {dragging.current=false;seek(e.currentTarget.valueAsNumber);}}}
        onLostPointerCapture={()=>{dragging.current=false;setDraft(null);}}/>
      <small>{clock(draft ?? state.ms)} / {clock(state.duration)}</small>
      <button onClick={()=>send({type:'playback',ms:state.duration,speed:0})}>Race result</button></>}
    <button onClick={()=>{location.search='';}}>Return to live</button></div>;
}
