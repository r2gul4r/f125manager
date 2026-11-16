import {useEffect, useRef} from 'react';
import type {Frame, Rejoin, TyreExit} from './timing';

type Snapshot = NonNullable<Frame['displayStamp']> & {
  lap:number; target:number; visible:boolean; basis:number; held:boolean;
  exit:Pick<Rejoin,'position'|'before'|'after'|'aheadGapMs'|'behindGapMs'|'lossMs'> & {
    rivalMargins?:[string,number][];validation?:TyreExit['validation'];penaltyMs?:number;lapPaceMs?:[string,number][];
  };
};
type Batch = {recording:string; samples:Snapshot[]};

// Batch transport only. An older frame in the same batch can survive a rewind.
export function usePitRecording(frame:Frame|null, status:string, view:string, cursor:number) {
  const queue = useRef<Batch[]>([]);
  useEffect(()=>{
    let busy=false;
    const flush=async()=>{
      if(busy || !queue.current.length) return;
      busy=true;
      const batch=queue.current.shift()!;
      try {
        const response=await fetch('/api/recordings/'+batch.recording+'/displayed-exits',{
          method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(batch.samples),keepalive:true
        });
        if(!response.ok) throw new Error('Pit recording HTTP '+response.status);
      } catch(error) {
        queue.current.unshift(batch);
        console.error('Pit display samples pending',error);
      } finally {busy=false;}
    };
    const timer=window.setInterval(()=>void flush(),500);
    const onHide=()=>{
      while(queue.current.length){
        const batch=queue.current[0];
        const body=new Blob([JSON.stringify(batch.samples)],{type:'application/json'});
        if(!navigator.sendBeacon('/api/recordings/'+batch.recording+'/displayed-exits',body)) break;
        queue.current.shift();
      }
    };
    window.addEventListener('pagehide',onHide);
    return ()=>{clearInterval(timer);window.removeEventListener('pagehide',onHide);void flush();};
  },[]);
  useEffect(()=>{
    const stamp=frame?.displayStamp, recording=frame?.recordingId;
    if(!frame || !recording || !stamp || status!=='Live' || frame.source!=='Live' || frame.recordingHold) return;
    const forecast=frame.forecast ?? frame.previousPlans;
    const basis=frame.forecast ? frame.predictionLap ?? frame.lap : frame.previousPlans?.lap;
    if(!forecast?.tyreExits || basis==null || basis>frame.lap) return;
    const shown=new Set(Array.from(document.querySelectorAll<HTMLElement>('[data-shown-exit]'))
      .filter(el=>el.getClientRects().length && document.visibilityState==='visible' && !document.querySelector('dialog[open]'))
      .map(el=>Number(el.dataset.shownExit)));
    if(!frame.forecast && !shown.size) return;
    let batch=queue.current.at(-1);
    if(!batch || batch.recording!==recording || batch.samples.length>40){
      batch={recording,samples:[]};queue.current.push(batch);
    }
    const first=frame.lap-basis;
    forecast.tyreExits.slice(first).forEach((row,offset)=>{
      const target=frame.lap+offset, visible=shown.has(target);
      if(offset>3 && !visible) return;
      if(!frame.forecast && !visible) return;
      const {position,before,after,aheadGapMs=null,behindGapMs=null,lossMs,rivalMargins,penaltyMs,lapPaceMs,validation}=row;
      const sample={...stamp,lap:frame.lap,target,visible,basis,held:!frame.forecast,
        exit:{position,before,after,aheadGapMs,behindGapMs,lossMs,rivalMargins,validation,penaltyMs,lapPaceMs}};
      const i=batch.samples.findIndex(s=>s.at===stamp.at && s.branch===stamp.branch && s.target===target && s.visible===visible);
      if(i<0) batch.samples.push(sample);
      else batch.samples[i]=sample;
    });
  },[frame,status,view,cursor]);
}
