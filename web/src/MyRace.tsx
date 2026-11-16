import type {CSSProperties} from 'react';
import {RankDriver} from './RankDriver';
import {rivalGap} from './PitReview';
import {TyreBadge} from './TyreBadge';
import {PaceHistory, paceWait, StintBar, StrategyAnalysis, SelectedPlan} from './RaceAnalysis';
import {LapReference} from './LapReference';
import {startingPlans, planSlots, type Editor} from './raceEditor';
import {compounds, type Car, type Compound, type Frame, type Pace} from './timing';
import {formatGap, formatLapTime} from './vendor/utils/formatters';
import './myRace.css';

function TyreLabel({compound, age, stintAge}: {compound:Compound|null; age?:number|null; stintAge?:boolean}) {
  return <span className="tyres race-tyre"><TyreBadge compound={compound}/>{' '}
    <span>{compound ? compounds[compound] : '—'}{age != null &&
      <small>{age} {age===1?'lap':'laps'} {stintAge?'this stint':'used'}</small>}</span></span>;
}

function GapStat({label, car, gap}: {label:string; car?:Car; gap?:number|null}) {
  return <div><h2>{label} <em>{car?.code ?? '—'}</em></h2>
    <strong>{gap == null ? '—' : <>{(gap/1000).toFixed(1)}<small>s</small></>}</strong></div>;
}

function PaceLine({label, pace, other,waiting,remaining}: {label:string; pace?:Pace|null; other?:Car; waiting:string; remaining:number}) {
  if (!other) return <div className="pace-empty">{label}　—　<span lang="ko">{label==='Chase'?'앞차 없음':'뒤차 없음'}</span></div>;
  const delta = pace?.deltaMs ?? 0;
  const seconds = Math.abs(delta) < 100 && delta !== 0 ? '0.1초 미만' : (Math.abs(delta)/1000).toFixed(1)+'초';
  const rate = delta===0?'격차 유지':'랩당 '+seconds+(delta>0?' 좁혀짐':' 벌어짐');
  const eta = pace?.laps;
  const headline = eta===0?'현재 1초 이내':pace?.sampleLaps===0?'랩 평균 대기':eta!=null && eta>remaining?'현재 페이스로는 완주 전 1초권 밖':eta!=null?eta+'랩 이내 1초 진입 예상':rate;
  return <div className="pace-line"><span className="pace-opponent">{label}
    {other ? <RankDriver car={other} rank={other.position}/> : ' —'}</span>
    <strong lang="ko">{pace ? headline : '분석 대기'}</strong>
    <small lang="ko">{pace ? [pace.gapMs!=null?'현재 간격 '+(pace.gapMs/1000).toFixed(1)+'초':null,
      eta!=null && pace.sampleLaps!==0?rate:null, eta!=null && eta>remaining?'잔여 거리 초과':null,
      pace.sampleLaps!==undefined ? (pace.sampleLaps ? '유효 '+pace.sampleLaps+'랩 평균 · L'+pace.lap+' 기준' : '유효 비교 랩 수집 중') : pace.windowMs?'최근 '+(pace.windowMs/1000).toFixed(1)+'초 기준':'L'+pace.lap+(pace.partialLap?' 주행 중 추정':' 완료 랩 기준')].filter(Boolean).join(' · ') : waiting}</small></div>;
}

export function MyRace({frame, cars, editor, select, ready,codex}: {
  frame:Frame; cars:Car[]; editor:Editor; select:(n:number,action?:'open')=>void;
  ready:boolean;

  codex:(type:'askCodex'|'applyCodex')=>void;
}) {
  const me = frame.cars[frame.player], index = cars.findIndex(c=>c.code===me.code);
  const ahead = cars[index-1], behind = cars[index+1];
  const grid = frame.mode==='grid', retired = me.retired, {cursor} = editor;
  const valid = !grid && !retired && !me.pit && (frame.source ? frame.flag!=='RED' : frame.flag==='TRACK CLEAR');
  const pace = frame.lapAnalysis ?? frame.analysis;
  const setup = frame.preRace;
  const fastestStarts = startingPlans(frame);
  const observedGap = !grid && !retired;
  const frontGap = ahead && observedGap && !ahead.retired ? me.intervalMs : null;
  const rearGap = behind && observedGap && !behind.retired ? behind.intervalMs : null;
  const gapDigits = (Math.max(frontGap ?? 0,rearGap ?? 0)/1000).toFixed(1).split('.')[0].length;
  const slots = planSlots(frame);
  const advisorSlot = slots.advisor;
  const planIndex = cursor-slots.first;
  return <div className="my-race"><main className="race-body" aria-label="My Race">
    <section className="race-observations">
      <div className="race-caption"><span className="signal-dot"/>Observed · {frame.recordingHold?'Last recording':frame.source ?? 'Demo'} {frame.lap>0 ? <LapReference label="Current lap" lap={frame.lap}/> : <span>Grid</span>}</div>
      <div className="battle-stats" style={{'--gap-digits':gapDigits} as CSSProperties}><div><h2>Position</h2><strong>{retired?'DNF':'P'+me.position}</strong></div>
        <GapStat label="Ahead" car={ahead} gap={frontGap}/>
        <GapStat label="Behind" car={behind} gap={rearGap}/></div>
      <section className="neighbors"><h2>Nearby Drivers</h2><table aria-label="Nearby Drivers"><thead><tr>
        {['DRIVER','GAP','INT','LAST LAP'].map(n=><th key={n}>{n}</th>)}</tr></thead><tbody>
        {cars.slice(Math.max(0,index-2),index+3).map(car=><tr key={car.code} data-driver={car.code} className={car===me?'me':''}>
          <td><RankDriver car={car} rank={car.position}/></td>
          <td>{grid || car.position===1 || car.gapMs==null?'—':'+'+formatGap(car.gapMs)}</td><td>{grid || car.position===1 || car.intervalMs==null?'—':'+'+formatGap(car.intervalMs)}</td>
          <td>{car.retired?'DNF':car.pit?'PIT':grid?'—':formatLapTime(car.lastMs)}</td></tr>)}</tbody></table></section>
      {frame.isRace!==false && <section className="pace"><h2>Pace <small>Forecast</small></h2><div className="pace-calls">
          <PaceLine label="Chase" other={ahead} remaining={(frame.totalLaps??27)-frame.lap+1} waiting={paceWait(frame,ready,ahead)} pace={valid && !ahead?.retired && !ahead?.pit && pace?.chase?.leader===ahead?.code ? pace?.chase:null}/>
          <PaceLine label="Defend" other={behind} remaining={(frame.totalLaps??27)-frame.lap+1} waiting={paceWait(frame,ready,behind)} pace={valid && !behind?.retired && !behind?.pit && pace?.defend?.follower===behind?.code ? pace?.defend:null}/>
        </div></section>}
      <section className="tyre-summary"><h2>Current Tyre</h2><div className="current-set"><TyreLabel compound={me.tyre} age={me.age} stintAge={me.stintAge}/>
        <div className="tyre-life">{frame.fittedLife!=null && <b title="Game estimate">{frame.fittedLife} laps left</b>}
        {me.wheelWear && <small>Max wear · {Math.max(...me.wheelWear).toFixed(1)}%</small>}</div></div></section>
      {setup && <section aria-label="Practice tyre measurements" className="fp-tyres"><h3>FP race-pace runs</h3>
        <small>Player · {setup.playerLaps} laps　 Field · {setup.fieldLaps} laps</small>
        <table><thead><tr><th>Tyre</th><th>FP pace</th><th>Pace trend / lap</th><th>Wear / lap</th></tr></thead>
        <tbody>{(Object.keys(setup.tyres) as Compound[]).map(t=>{
          const m=setup.tyres[t]!;
          return <tr key={t}><td><TyreBadge compound={t}/></td><td>{formatLapTime(m.paceMs)}<small>{m.source} · {m.laps} laps</small></td>
            <td>{m.trendMs==null?'—':(m.trendMs>0?'+':'')+(m.trendMs/1000).toFixed(3)+' s'}<small>{m.trendSource} · {m.pairs} pairs</small></td>
            <td>{m.wearPct==null?'—':m.wearPct.toFixed(2)+' pp'}<small>{m.wearSource} · {m.wearLaps} laps</small></td></tr>
        })}</tbody></table></section>}
      <PaceHistory source={frame.source} rows={frame.paceHistory ?? []}/>
      {frame.lastPitExit && <p aria-label="Last pit exit" className="race-note">피트 복귀 P{frame.lastPitExit.position}
        {frame.lastPitExit.before && <> · 앞 {rivalGap(frame.lastPitExit.before,frame.lastPitExit.aheadGapMs,'측정 불가')}</>}
        {frame.lastPitExit.after && <> · 뒤 {rivalGap(frame.lastPitExit.after,frame.lastPitExit.behindGapMs,frame.lastPitExit.waiting?'통과 대기':'측정 불가')}</>}</p>}
    </section><section className="race-strategy"><div className="strategy-title"><h2>Pit Strategy</h2>
      <span role="status" aria-label="Race phase">{frame.isRace===false?frame.sessionName:retired?'DNF':grid?'Pre-race':frame.sessionName ?? 'Racing'}</span></div>
      {setup && <section aria-label="Pre-race recommendation" className="grid-setup">
        <h3>{fastestStarts.length>1?'Equal projected time':'Recommended stints'}</h3>
        {fastestStarts.map((plan,i)=><button key={plan.start} aria-label={'Apply starting plan · '+plan.start} aria-pressed={cursor===i} disabled={!ready || frame.canPlan===false} onClick={()=>select(i,'open')}><StintBar plan={plan} total={frame.totalLaps}/></button>)}
        {!fastestStarts.length && <small lang="ko">관측값과 가용 세트로 완주 계획을 계산할 수 없음</small>}
        {!setup.inventoryKnown && <small lang="ko">게임 타이어 재고 대기</small>}
      </section>}
      {frame.isRace!==false && !retired && <SelectedPlan frame={frame}/>}
      {!retired && (frame.forecast || (frame.isRace && !grid && frame.lap<(frame.totalLaps??0))) && <StrategyAnalysis frame={frame} ready={ready} index={planIndex} select={i=>select(i+slots.first)}
        apply={i=>select(i+slots.first,'open')}/>}
      <p className="race-note" lang="ko" role="status">{editor.message ?? frame.notice}</p>
      {frame.gameSync && <p className="race-note" lang="ko" role="status">{frame.gameSync}</p>}
      {frame.advisor && !retired && <div className="codex-actions">
        <button aria-pressed={cursor===advisorSlot} disabled={frame.microphoneMode || !ready || !frame.advisor.available || frame.advisor.pending} aria-busy={frame.advisor.pending || frame.radioStatus==='thinking'} onClick={()=>codex('askCodex')}>{frame.microphoneMode?({thinking:'Codex thinking…',listening:'Radio listening…',transcribing:'Transcribing…',speaking:'Engineer speaking…'}[frame.radioStatus??''] ?? 'Radio · UDP 3'):frame.advisor.pending?'Codex thinking…':'Request Codex plan'}</button>
        {frame.advisor.plan && <><button aria-pressed={cursor===advisorSlot+1} disabled={!ready || !frame.advisor.available} onClick={()=>codex('applyCodex')}>{frame.recordingHold || frame.source==='Replay'?'Apply to replay':'Apply Codex plan'}</button>
          {'start' in frame.advisor.plan && <StintBar plan={frame.advisor.plan} total={frame.totalLaps}/>}
          <p lang="ko">{frame.advisor.reason}</p></>}
        {frame.advisor.message && <small role="status">{frame.advisor.message}</small>}
      </div>}
    </section></main></div>;
}

