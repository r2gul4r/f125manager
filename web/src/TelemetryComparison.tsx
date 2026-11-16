import {useEffect,useState} from 'react';
import {formatLapTime} from './vendor/utils/formatters';

type Lap = {lap:number;ms:number;sectors:number[];valid:boolean};
type Sample = [number,number,[number, number, number|null, number|null, number|null, number]];
type Analysis = {session:string;length:number|null;laps:Lap[];samples:Sample[];held?:boolean};
const channels = ['Speed (km/h)','Throttle (%)','Brake (%)','ERS (MJ)','Tyre surface (°C)'];

export function TelemetryComparison({recording}:{recording:string}) {
  const [data,show]=useState<Analysis|null>(null),[error,fail]=useState(false);
  const [first,pickFirst]=useState(0),[second,pickSecond]=useState(0),[channel,pickChannel]=useState(0);
  useEffect(()=>{
    const abort=new AbortController();
    let timer:ReturnType<typeof setTimeout>;
    async function read(){
      try {
        const res=await fetch('/api/analysis/'+encodeURIComponent(recording),{signal:abort.signal,cache:'no-store'});
        if(!res.ok)throw new Error();
        show(await res.json()); fail(false);
      } catch {if(!abort.signal.aborted)fail(true);}
      if(!abort.signal.aborted && recording==='live')timer=setTimeout(read,1500);
    }
    void read();
    return ()=>{abort.abort();clearTimeout(timer);};
  },[recording]);
  if(error || !data)return <p role="status">{error?(recording==='live'?'텔레메트리 수신 대기':'녹화 텔레메트리를 읽을 수 없음'):'Loading telemetry…'}</p>;
  const laps=[...new Set([...data.laps.map(l=>l.lap),...data.samples.map(s=>s[0])])].sort((a,b)=>a-b);
  if(!laps.length)return <p>{recording==='live'?'플레이어 랩 데이터 대기':'이 녹화본에 비교할 플레이어 랩 기록 없음'}</p>;
  const a=laps.includes(first)?first:laps.at(-1)!, b=laps.includes(second)?second:laps.at(-2)??a;
  const groups=[a,b].map(n=>data.samples.filter(s=>s[0]===n));
  const max=Math.max(1,...groups.flat().map(s=>s[2][channel+1]??0));
  const options=laps.map(n=><option key={n} value={n}>L{n}</option>);
  function exportData(){
    const href=URL.createObjectURL(new Blob([JSON.stringify({source:recording,channels:['distance (m)',...channels],...data})],{type:'application/json'}));
    const link=document.createElement('a');link.href=href;link.download='telemetry-'+recording+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(href),1000);
  }
  return <section aria-label="Observed telemetry"><h3>Lap comparison · {data.held?'Last recording':recording==='live'?'Live UDP':'Recorded UDP'}</h3>
    <div className="panel-tools"><label>Lap A <select value={a} onChange={e=>pickFirst(+e.target.value)}>{options}</select></label>
      <label>Lap B <select value={b} onChange={e=>pickSecond(+e.target.value)}>{options}</select></label>
      <label>Channel <select value={channel} onChange={e=>pickChannel(+e.target.value)}>{channels.map((c,i)=><option key={c} value={i}>{c}</option>)}</select></label>
      <button onClick={exportData}>Export telemetry</button></div>
    {groups.some(g=>g.length>0) && <><p>Lap A · Yellow　 Lap B · White　 ·　 0–{data.length} m　 ·　 0–{max.toFixed(1)} {channels[channel]}</p>
      <svg className="trace-chart" viewBox="0 0 600 120" role="img" aria-label={channels[channel]+' by lap distance'}>
        {groups.map((samples,i)=>{let previous=-2;let path='';
          const points=samples.flatMap(([,bin,values])=>{const value=values[channel+1];if(value==null)return [];
            const x=values[0]*600/(data.length||1),y=115-value/max*110;
            path+=(bin===previous+1?'L':'M')+x+' '+y+' ';previous=bin;return [{x,y,bin}];});
          const color=i?'white':'#ffe469';
          return <g key={i}><path d={path} fill="none" stroke={color} strokeDasharray={i?'5 3':undefined}/>
            {points.map(p=><circle key={p.bin} cx={p.x} cy={p.y} r="2" fill={color}/>)}</g>;})}
      </svg></>}
    <table><thead><tr>{['Lap','S1','S2','S3','Lap time'].map(c=><th key={c}>{c}</th>)}</tr></thead>
      <tbody>{[a,b].map((n,i)=>{const lap=data.laps.find(l=>l.lap===n);return <tr key={i}><td>{i?'B':'A'} · L{n}{lap && !lap.valid?' · Invalid':''}</td>
        {[0,1,2].map(j=><td key={j}>{lap?.sectors[j]?(lap.sectors[j]/1000).toFixed(3):'—'}</td>)}<td>{lap?formatLapTime(lap.ms):'—'}</td></tr>;})}</tbody></table></section>;
}
