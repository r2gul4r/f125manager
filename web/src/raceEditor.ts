import type {Action, Frame, ForecastPlan, Plan} from './timing.ts';

export interface Editor {cursor:number; message?:string}

export function pitSchedule(plan:Omit<ForecastPlan,'id'>,frame:Frame) {
  if (plan.stops) return plan.stops;
  const later = frame.mode==='grid'?[]:frame.plan.stops.filter(s=>s.lap>=frame.lap).slice(1).filter(s=>s.lap>plan.stop.lap);
  return [plan.stop,...later];
}

export function startingPlans(frame:Frame) {
  const plans=frame.mode==='grid'?frame.preRace?.plans:undefined;
  return plans?.filter(p=>p.modelMs===plans[0].modelMs) ?? [];
}

export function planSlots(frame:Frame) {
  const first=startingPlans(frame).length;
  const advisor=first+((frame.forecast ?? frame.previousPlans)?.plans.length ?? 0);
  return {first,advisor,count:advisor+(frame.advisor?.available?1+Number(!!frame.advisor.plan):0)};
}

export function editPlan(state:Editor,action:Action,frame:Frame): {editor:Editor;confirm?:Plan;replaceFuture?:boolean;advisor?:'askCodex'|'applyCodex'} {
  const {cursor}=state;
  const slots=planSlots(frame);
  if (action==='back' || !slots.count || frame.canPlan===false || !frame.cars[frame.player] || frame.cars[frame.player].retired)
    return {editor:{cursor:0}};
  if (action!=='ok') {
    const step=action==='up' || action==='left'?-1:1;
    for (let offset=1;offset<=slots.count;offset++) {
      const next=(cursor+step*offset+slots.count)%slots.count;
      if (!(frame.forecast ?? frame.previousPlans)?.plans[next-slots.first]?.codexExpired) return {editor:{cursor:next}};
    }
    return {editor:state};
  }
  if (cursor>=slots.advisor && frame.advisor?.available) {
    if (frame.advisor.pending) return {editor:state};
    return {editor:state,advisor:cursor===slots.advisor?'askCodex':frame.advisor.plan?'applyCodex':undefined};
  }
  const starting=startingPlans(frame)[cursor];
  const strategy=frame.forecast?.plans[cursor-slots.first];
  if (strategy?.codexExpired) return {editor:state};
  const stops=strategy ? pitSchedule(strategy,frame) : starting?.stops;
  if (!stops) return {editor:state};
  if (stops.some(s=>s.lap<Math.max(1,frame.lap) || (frame.availableTyres && !frame.availableTyres.includes(s.tyre))))
    return {editor:{cursor,message:'랩 또는 가용 타이어 변경 · 플랜을 다시 선택해'}};
  return {editor:{cursor},confirm:{start:starting?.start ?? frame.plan.start,
    stops:structuredClone(frame.source || frame.mode==='grid'?stops:stops.slice(0,1))},replaceFuture:!!frame.source};
}
