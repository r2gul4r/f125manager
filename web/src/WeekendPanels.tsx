import {useEffect, useState} from 'react';
import {archive, channels, lapTime, trace, type Channel, type DemoLap} from './demoWeekend';
import {TyreBadge} from './TyreBadge';
import {compounds} from './timing';
import {formatLapTime, formatSignedDelta} from './vendor/utils/formatters';

function LapComparison({record}:{record:typeof archive[number]}) {
  const clean=record.laps.filter(l=>l.condition==='Clean');
  const [first,pickFirst]=useState(clean[0].lap), [second,pickSecond]=useState(clean[1].lap);
  const [channel,pickChannel]=useState<Channel>('Speed'), [sample,setSample]=useState(0);
  const a=clean.find(l=>l.lap===first)!, b=clean.find(l=>l.lap===second)!;
  const profile=channels[channel], av=trace(channel,a,record), bv=trace(channel,b,record);
  function points(values:number[]) {
    return values.map((v,i)=>[i*600/(values.length-1),115-v/profile.max*108].join(',')).join(' ');
  }
  const options=clean.map(l=><option key={l.lap} value={l.lap}>L{l.lap} · {compounds[l.tyre]} · {formatLapTime(lapTime(l))}</option>);
  return <><div className="panel-tools">
    <label>Lap A <select aria-label="Lap A" value={first} onChange={e=>pickFirst(+e.target.value)}>{options}</select> <TyreBadge compound={a.tyre}/></label>
    <label>Lap B <select aria-label="Lap B" value={second} onChange={e=>pickSecond(+e.target.value)}>{options}</select> <TyreBadge compound={b.tyre}/></label>
    <label>Channel <select value={channel} onChange={e=>pickChannel(e.target.value as Channel)}>{Object.keys(channels).map(c=><option key={c}>{c}</option>)}</select></label></div>
    <h3>{channel} · {profile.unit}</h3>
    <svg className="trace-chart" viewBox="0 0 600 124" role="img" aria-label={channel+' comparison by lap distance'}>
      {[7,61,115].map(y=><line key={y} x1="0" x2="600" y1={y} y2={y} stroke="#45454d"/>)}
      <polyline points={points(av)} fill="none" stroke="#ffe469" strokeWidth="2.5"/>
      <polyline points={points(bv)} fill="none" stroke="#e9eaf0" strokeDasharray="6 3" strokeWidth="2"/>
      <line x1={sample*600/11} x2={sample*600/11} y1="0" y2="120" stroke="#ef4949"/></svg>
    <label className="scrubber">Distance · {Math.round(record.metres*sample/11)} m
      <input type="range" min="0" max="11" value={sample} onChange={e=>setSample(+e.target.value)}/></label>
    <p className="trace-key"><b>Lap A · {av[sample]} {profile.unit}</b>　 Lap B · {bv[sample]} {profile.unit}</p>
    <table><thead><tr>{['Lap','S1','S2','S3','Lap time','Δ to A'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>
      {[a,b].map((l,i)=><tr key={i}><td>{i?'B':'A'} · L{l.lap}</td>{l.sectors.map((v,j)=><td key={j}>{(v/1000).toFixed(3)}</td>)}
        <td>{formatLapTime(lapTime(l))}</td><td>{formatSignedDelta(lapTime(l)-lapTime(a))} s</td></tr>)}</tbody></table>
    <details><summary>Sector trend · All clean laps</summary><table><thead><tr>{['Lap','S1 (s)','S2 (s)','S3 (s)'].map(t=><th key={t}>{t}</th>)}</tr></thead>
      <tbody>{clean.map(l=><tr key={l.lap}><td>L{l.lap}</td>{l.sectors.map((ms,i)=><td key={i}>{(ms/1000).toFixed(3)}</td>)}</tr>)}</tbody></table></details></>;
}

function exportSession(record:typeof archive[number]) {
  const href=URL.createObjectURL(new Blob([JSON.stringify({source:'Demo',...record},null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=href;link.download=record.gp+'-'+record.session+'-demo.json';link.click();
  setTimeout(()=>URL.revokeObjectURL(href),1000);
}

const grandsPrix = [...new Set(archive.map(record=>record.gp))];

export function SessionAnalysis() {
  const [view,setView]=useState('telemetry');
  const [gp,setGp]=useState('');
  const [query,search]=useState(''), [kind,filter]=useState('All'), [session,pick]=useState(0);
  const records=archive.filter(s=>(!gp||s.gp===gp) && (kind==='All'||s.session===kind) && (s.gp+' '+s.session).toLowerCase().includes(query.trim().toLowerCase()));
  const record=records[session] ?? records[0];
  return <><div className="panel-tools"><span>Demo archive · 2026</span>
    <label>Grand Prix <select aria-label="Grand Prix" value={gp} onChange={e=>{setGp(e.target.value);search('');pick(0);}}>
      <option value="">All GPs</option>{grandsPrix.map(name=><option key={name}>{name}</option>)}</select></label>
    <label>Search GP <input type="search" value={query} onChange={e=>{search(e.target.value);setGp('');pick(0);}}/></label>
    <label>Session type <select value={kind} onChange={e=>{filter(e.target.value);pick(0);}}>{['All','FP1','Race'].map(s=><option key={s}>{s}</option>)}</select></label></div>
    {record ? <><div className="panel-tools"><label>Session <select aria-label="Session" value={session} onChange={e=>pick(+e.target.value)}>{records.map((s,i)=>
      <option value={i} key={s.gp+s.session}>{s.gp} · {s.session}</option>)}</select></label>
      <label>View <select aria-label="View" value={view} onChange={e=>setView(e.target.value)}>
        <option value="telemetry">Lap comparison</option><option value="replay">Session replay</option></select></label></div>
      {view==='replay'?<ArchiveReplay record={record} key={record.gp+record.session}/>:
        <LapComparison record={record} key={record.gp+record.session}/>}</> : <p lang="ko">검색 조건에 맞는 세션이 없음.</p>}</>;
}

function ArchiveReplay({record}:{record:typeof archive[number]}) {
  const [stint,selectStint]=useState(0), [index,seek]=useState(0), [playing,play]=useState(false);
  const laps=record.laps.filter(l=>!stint||stint===l.stint), lap=laps[index], last=laps.length-1;
  function decision(entry:DemoLap) {
    const previous=record.laps[record.laps.indexOf(entry)-1];
    if (entry.condition==='Pit' && previous)
      return <>Box · <TyreBadge compound={previous.tyre}/> → <TyreBadge compound={entry.tyre}/></>;
    return entry.decision;
  }
  useEffect(()=>{
    if (!playing) return;
    if(index>=last){play(false);return;}
    const timer=setTimeout(()=>seek(index+1),850);
    return ()=>clearTimeout(timer);
  },[playing,index,last]);
  return <><div className="panel-tools"><label>Stint <select value={stint} onChange={e=>{play(false);seek(0);selectStint(+e.target.value);}}>
    <option value={0}>All stints</option>{[...new Set(record.laps.map(l=>l.stint))].map(s=><option key={s} value={s}>Stint {s}</option>)}</select></label>
    </div>
    <h3>Lap replay · L{lap.lap}</h3><div className="panel-tools"><button onClick={()=>{if(index===last)seek(0);play(!playing);}}>{playing?'Pause':'Play'}</button>
      <label className="scrubber">Replay lap <input type="range" min="0" max={last} value={index} onChange={e=>{play(false);seek(+e.target.value);}}/></label></div>
    <div className="work-scroll"><table><thead><tr>{['Lap','Stint','Tyre','Lap time','State','Decision'].map(h=><th key={h}>{h}</th>)}</tr></thead>
    <tbody>{laps.map((l,i)=><tr key={l.lap} data-active={i===index}><td><button onClick={()=>{seek(i);play(false);}}>L{l.lap}</button></td>
      <td>{l.stint}</td><td><TyreBadge compound={l.tyre}/></td><td>{formatLapTime(lapTime(l))}</td><td>{l.condition}</td><td>{decision(l)}</td></tr>)}</tbody></table></div>
    <dl className="metric-list"><div><dt>Prediction · prior lap</dt><dd>P{lap.forecast}</dd></div><div><dt>Observed · L{lap.lap}</dt><dd>P{lap.position}</dd></div>
      <div><dt>Position error</dt><dd>{Math.abs(lap.position-lap.forecast)} places</dd></div></dl>
    <p>{decision(lap)} · {lap.condition} · {lap.sectors.map((s,i)=>'S'+(i+1)+' '+(s/1000).toFixed(3)+' s').join(' / ')}</p>
    <button onClick={()=>exportSession(record)}>Export session</button></>;
}

const diagnostics={
  Healthy:{stream:'Receiving',rate:'60 Hz',loss:'0.1%',age:'65 ms',storage:'Recording',agent:'Connected'},
  Stale:{stream:'Stale',rate:'2 Hz',loss:'8.4%',age:'2,400 ms',storage:'Waiting for packets',agent:'Offline'},
  Disconnected:{stream:'Disconnected',rate:'0 Hz',loss:'—',age:'—',storage:'Idle',agent:'Offline'},
};
export function Diagnostics({status}:{status:string}) {
  const [scenario,pick]=useState<keyof typeof diagnostics>('Healthy');
  const [format,setFormat]=useState('2026');
  const d=diagnostics[scenario];
  return <><p>Dashboard connection · {status}</p><div className="panel-tools"><label>Demo signal <select value={scenario}
    onChange={e=>pick(e.target.value as keyof typeof diagnostics)}>{Object.keys(diagnostics).map(k=><option key={k}>{k}</option>)}</select></label>
    <label>Fixture format <select value={format} onChange={e=>setFormat(e.target.value)}><option>2026</option><option>2025</option></select></label></div>
    <h3>Simulated diagnostics</h3><dl className="metric-list">{Object.entries({'UDP format':format,'Packet stream':d.stream,'Packet rate':d.rate,
      'Estimated loss':d.loss,'Snapshot age':d.age,'Storage':d.storage,'Codex connection':d.agent}).map(([name,value])=>
      <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>
    <p lang="ko">선택한 상태를 재현하는 더미 진단값임. 실제 장치에는 설정을 전송하지 않음.</p></>;
}
