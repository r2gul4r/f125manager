import {Fragment, useEffect, useState} from 'react';
import type {MeasuredExit} from './timing';

interface Exit {
  position:number; before:string|null; after:string|null; aheadGapMs:number|null; behindGapMs:number|null;
}
interface Visit {
  entryMs:number; lap:number; forecasts:({at:number;visible:boolean;basis:number;held:boolean;target:number}&Exit|null)[];
  actual:MeasuredExit|null;
  review?:{scores:(string|null)[];facts:string[];learning:string};
}
function clock(ms:number) {
  return Math.floor(ms/60000)+':'+String(Math.floor(ms%60000/1000)).padStart(2,'0');
}
export function rivalGap(code:string|null|undefined, gap:number|null|undefined, missing='—') {
  return code ? code+' · '+(gap==null?missing:(gap/1000).toFixed(3)+'s') : '—';
}
function Cells({row,measured=false}:{row?:MeasuredExit|null;measured?:boolean}) {
  const missing=measured?'측정 불가':'—';
  return <><td>{row?'P'+row.position:'—'}</td><td>{rivalGap(row?.before,row?.aheadGapMs,missing)}</td>
    <td>{rivalGap(row?.after,row?.behindGapMs,missing)}</td></>;
}
export function PitReview({recording,revision,expectedStops}:{recording:string;revision?:number;expectedStops?:number}) {
  const [visits,setVisits]=useState<Visit[]|null>(null);
  const [error,setError]=useState(false);
  useEffect(()=>{
    const controller=new AbortController();
    let retry=0;
    async function load(){
      try{
        const response=await fetch('/api/recordings/'+encodeURIComponent(recording)+'/pit-review',{signal:controller.signal});
        if(!response.ok) throw new Error();
        const rows:Visit[]=await response.json();
        if(!controller.signal.aborted){
          setVisits(rows);setError(false);
          if(expectedStops!=null && rows.length<expectedStops) retry=window.setTimeout(()=>void load(),2000);
        }
      }catch{
        if(!controller.signal.aborted){setError(true);retry=window.setTimeout(()=>void load(),3000);}
      }
    }
    void load();
    return ()=>{controller.abort();clearTimeout(retry);};
  },[recording,revision,expectedStops]);
  return <section className="pit-results" aria-label="Pit forecast review"><h3>피트 복귀 복기</h3>
    {error && <p role="status">녹화 읽기 재시도 중</p>}
    {!error && visits===null && <p role="status">피트 기록 읽는 중</p>}
    {!error && visits?.length===0 && <p>완료된 피트 기록 없음</p>}
    {visits?.map(v=><Fragment key={v.entryMs}><table><caption>L{v.lap} 피트 · {clock(v.entryMs)}</caption>
      <thead><tr><th>시점</th><th>출처</th><th>복귀 순위</th><th>앞차 · 간격</th><th>뒤차 · 간격</th><th>실측과 비교</th></tr></thead>
      <tbody>{v.forecasts.map((s,i)=><tr key={i}><th>{i===3?'진입 직전':(3-i)+'랩 전'}</th>
        <td>{s?(s.visible?'화면 표시':'계산 · 미표시')+' · '+(i===3?'진입 '+((v.entryMs-s.at)/1000).toFixed(1)+'초 전':clock(s.at))+(s.target!==v.lap?' · L'+s.target+' 피트 가정':'')+(s.held?' · L'+s.basis+' 예측 유지':''):'미기록'}</td><Cells row={s}/><td>{v.review?.scores[i]??'—'}</td></tr>)}
        <tr><th>실제 출구</th><td>같은 지점 통과 시차</td><Cells row={v.actual} measured/><td>—</td></tr>
      </tbody></table>{v.review && <div className="pit-review-findings"><ul>{v.review.facts.map(f=><li key={f}>{f}</li>)}</ul><p>{v.review.learning}</p></div>}</Fragment>)}</section>;
}
