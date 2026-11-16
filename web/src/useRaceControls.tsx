import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {planSlots,editPlan, type Editor} from './raceEditor';
import {DisplaySettings} from './DisplaySettings';
import {CodexSettings} from './CodexSettings';
import {Diagnostics} from './WeekendPanels';
import {operateTool, screenOrder, screens, type Screen} from './screens';
import type {Action, Frame, UdpInfo} from './timing';

type WheelAction = Action | Screen | 'nextScreen' | 'previousScreen';
type UdpAction = WheelAction | 'askCodex';
const labels: Record<WheelAction,string> = {...screens, previousScreen:'Previous screen', nextScreen:'Next screen', up:'Move up', down:'Move down', left:'Decrease', right:'Increase', ok:'Confirm', back:'Cancel'};
const shortcuts: Record<string,WheelAction> = {'1':'A','2':'B','[':'previousScreen',']':'nextScreen',ArrowUp:'up',ArrowDown:'down',ArrowLeft:'left',ArrowRight:'right',Enter:'ok',Escape:'back'};
const storageKey = 'pitwall.sdl.bindings';
type Bindings = Record<string,WheelAction>;
const udpBindings: Record<string,UdpAction> = {
  'udp/1':'previousScreen', 'udp/2':'nextScreen', 'udp/3':'askCodex', 'udp/4':'back',
  'udp/5':'up', 'udp/6':'down', 'udp/7':'left', 'udp/8':'right', 'udp/9':'ok',
};
function validBindings(value:unknown): Bindings {
  if (!value || typeof value !== 'object') return {};
  return Object.fromEntries(Object.entries(value).filter(([,v])=>Object.hasOwn(labels,v)));
}
function readBindings(legacy?:Record<string,string>): Bindings {
  const saved = localStorage.getItem(storageKey);
  return validBindings(saved ? JSON.parse(saved) : legacy);
}

export function canInteract(status:string) {
  return ['Demo','Live','Paused','Stale data','UDP disconnected','Last recording','Replay'].includes(status);
}

export function useRaceControls(frame:Frame|null, status:string, send:(data:object)=>boolean, udp:UdpInfo|null,idleKeys:string[],replay:boolean) {
  const ready=canInteract(status);
  const [tab,setTab] = useState<Screen>(replay?'B':'A');
  const raceScreen = useRef<'A'|'B'>(replay?'B':'A');
  const [editor,setEditor] = useState<Editor>({cursor:0});
  const [mapping,setMapping] = useState(false);
  const [target,setTarget] = useState<WheelAction|null>(null);
  const [bindings,setBindings] = useState<Bindings>(()=>{try{return readBindings();}catch{return {};}});
  const [feedback,setFeedback] = useState('');
  const [direct,setDirect] = useState(()=>localStorage.getItem('pitwall.liveInput')==='direct');
  const liveInput = !replay && status!=='Demo';
  const useUdp = liveInput && !direct;
  function switchInput(value:boolean) {
    localStorage.setItem('pitwall.liveInput',value?'direct':'udp');
    setDirect(value); listen(null);
  }
  const state = useRef({tab,editor,target});
  const lastToken = useRef<string | undefined>(undefined);
  const lastPhase = useRef('');
  const initialized = useRef(false);
  function update(e:Editor) {state.current.editor = e; setEditor(e);}
  function navigate(t:Screen) {
    if (t==='A' || t==='B') raceScreen.current=t;
    state.current.tab = t;
    setTab(t);
  }
  function act(action:UdpAction) {
    if (mapping || document.querySelector('dialog[open], #race-menu:popover-open')) return;
    if (action==='A' || action==='B' || action==='analysis') {navigate(action); return;}
    const current = state.current.tab;
    if (action==='askCodex') {
      if (current==='B') codex(action);
      return;
    }
    if (action==='nextScreen' || action==='previousScreen') {
      const step=action==='nextScreen'?1:-1;
      navigate(screenOrder[(screenOrder.indexOf(current)+step+screenOrder.length)%screenOrder.length]);
      return;
    }
    if (current!=='A' && current!=='B') {
      if (action==='back') navigate(raceScreen.current);
      else operateTool(action);
      return;
    }
    if(replay){
      if(action==='back') navigate('analysis');
      else operateTool(action,current==='B'?':is(.replay-tools,.plan-comparison,.codex-actions)':'.replay-tools');
      return;
    }
    if (!ready || !frame || !frame.cars[frame.player] || state.current.tab!=='B') return;
    choose(action);
  }
  function choose(action:Action) {
    if (!ready || !frame) return;
    const result = editPlan(state.current.editor,action,frame);
    if (result.advisor) codex(result.advisor);
    update(result.editor);
    requestAnimationFrame(()=>document.querySelector('.race-strategy :is(button[aria-pressed="true"],button[data-current="true"])')?.scrollIntoView({block:'nearest'}));
    if (result.confirm && !send({type:'confirm',token:frame.token,planId:frame.forecast?.plans[state.current.editor.cursor-planSlots(frame).first]?.id,proposalId:frame.advisor?.id,replaceFuture:!!result.replaceFuture,...result.confirm}))
      update({cursor:0,message:'연결 대기 · 적용 실패'});
  }
  function codex(type:'askCodex'|'applyCodex') {
    if (!ready || !frame?.advisor?.available || !frame.cars[frame.player] || frame.cars[frame.player].retired) return;
    if (type==='askCodex' && frame.advisor.pending) return;
    send({type,token:frame.token,id:frame.advisor.id,stops:frame.advisor.plan?.stops});
  }
  function listen(t:WheelAction|null) {state.current.target=t; setTarget(t);}
  function save(next:Bindings) {
    try {
      localStorage.setItem(storageKey,JSON.stringify(next)); setBindings(next); setFeedback('매핑 저장됨');
    } catch {setFeedback('브라우저 저장소에 매핑을 저장할 수 없음');}
    listen(null);
  }
  function wheelKey(key:string) {
    if (key.startsWith('udp/') !== useUdp) return;
    if (mapping) {
      const action=state.current.target;
      if (action && !useUdp) save({...bindings,[key]:action});
      return;
    }
    const action=(useUdp ? udpBindings : bindings)[key];
    if (action) act(action);
  }
  useLayoutEffect(()=>{idleKeys.forEach(wheelKey);},[idleKeys]);
  useLayoutEffect(()=>{
    if (!frame) return;
    if (lastToken.current !== frame.token) {
      lastToken.current = frame.token;
      const phase = frame.session + ':' + frame.mode;
      if (lastPhase.current !== phase) update({cursor:0});
      lastPhase.current = phase;
    }
    if (!initialized.current) {
      initialized.current=true;
      try {setBindings(readBindings(frame.wheel?.bindings));}
      catch {setBindings(validBindings(frame.wheel?.bindings));setFeedback('저장 매핑 읽기 실패 · 기본 매핑 사용');}
    }
    frame.wheel?.keys.forEach(wheelKey);
  },[frame]); // Process each received batch once, including several edges between snapshots.
  useEffect(()=>{
    function onKey(e:KeyboardEvent) {
      if (mapping || document.querySelector('dialog[open], #race-menu:popover-open') || e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.target instanceof HTMLInputElement && e.target.type!=='range' && e.key!=='Escape') return;
      const action = shortcuts[e.key];
      const current=state.current.tab;
      if (!action) return;
      const navigation=action==='A' || action==='B' || action==='previousScreen' || action==='nextScreen';
      if (!navigation && ((!replay && current==='A') || (current==='analysis' && action!=='back') ||
        (!replay && current==='B' && e.target instanceof HTMLSelectElement))) return;
      if (e.key==='Enter' && e.target instanceof HTMLElement && e.target.matches('summary,button:focus-visible')) return;
      e.preventDefault();
      if (!replay && (action==='up' || action==='down')) {
        if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
      }
      if (!e.repeat) act(action);
    }
    window.addEventListener('keydown',onKey);
    return ()=>window.removeEventListener('keydown',onKey);
  });
  return {tab,navigate,editor,select:(cursor:number, action?:'open')=>{
    update({cursor});
    if (action==='open') choose('ok');
  },act,codex,
    openSettings:()=>{listen(null);setFeedback('');setMapping(true);}, dialog:mapping && <SettingsDialog udp={udp} status={status} device={frame?.wheel?.device}
      liveInput={liveInput} useUdp={useUdp} switchInput={switchInput} bindings={bindings} target={target} listen={listen} feedback={feedback}
      clear={a=>save(Object.fromEntries(Object.entries(bindings).filter(([,v])=>v!==a)))}
      close={()=>{setMapping(false);listen(null);document.getElementById('race-menu-button')?.focus();}}/>};
}

function SettingsDialog({udp,status,device,liveInput,useUdp,switchInput,bindings,target,listen,feedback,clear,close}: {
  liveInput:boolean; useUdp:boolean; switchInput:(direct:boolean)=>void;
  udp:UdpInfo|null; status:string; device?:string; bindings:Bindings; target:WheelAction|null; listen:(a:WheelAction|null)=>void;
  feedback:string; clear:(a:WheelAction)=>void; close:()=>void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [diagnostics,showDiagnostics]=useState(false);
  const [mic,setMic]=useState<{enabled:boolean;status:string;error?:string;latencyMs?:number|null}|null>(null);
  const [micError,setMicError]=useState('');
  useEffect(()=>{
    let active=true;
    async function read(){
      try {const res=await fetch('/api/settings/microphone'); if(res.ok){const data=await res.json();if(active)setMic(data);}}
      catch { /* The settings are polled again after reconnection. */ }
    }
    void read();const timer=setInterval(read,750);
    return ()=>{active=false;clearInterval(timer);};
  },[]);
  async function toggleMic(enabled:boolean){
    try {
      const res=await fetch('/api/settings/microphone',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled})});
      const data=await res.json();if(!res.ok)throw Error(data.detail);
      setMic(data);setMicError('');
    } catch(e){setMicError(String(e));}
  }
  useEffect(()=>{ref.current?.showModal();},[]);
  return <dialog ref={ref} className="wheel-dialog" aria-label="Settings" onCancel={e=>{e.preventDefault();ref.current?.close();}} onClose={close}>
    <div className="settings-heading"><h2>Settings</h2><button aria-pressed={diagnostics} onClick={()=>{listen(null);showDiagnostics(!diagnostics);}}>
      {diagnostics?'Back to settings':'Diagnostics'}</button></div>
    {diagnostics ? <section aria-label="Diagnostics"><h3>Diagnostics</h3>{udp ? <dl className="metric-list">{Object.entries({Address:udp.address,Status:udp.status,Format:udp.format || '—',Accepted:udp.accepted,Rejected:udp.rejected,'Timing age':udp.ageMs==null?'—':udp.ageMs+' ms','Recording drops':udp.recordDropped??0,'Recording error':udp.recordError || '—',Error:udp.error || '—'}).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl> : status==='Demo'?<Diagnostics status={status}/>:<p>{status} · Live UDP diagnostics unavailable</p>}</section> : <div className="settings-sections"><div className="settings-display"><DisplaySettings/><section><h3>Race radio</h3><label><input type="checkbox" role="switch" checked={mic?.enabled??false} disabled={!mic} onChange={e=>void toggleMic(e.target.checked)}/> Microphone mode</label>
    {mic?.enabled && <small role="status"> UDP 3 · {mic.status}{mic.latencyMs!=null && ` · Last reply ${(mic.latencyMs/1000).toFixed(2)} s after speech`}</small>}{(micError||mic?.error) && <p role="alert">{micError||mic?.error}</p>}</section><CodexSettings/></div><section className="settings-wheel"><h3>Wheel Mapping</h3><p>{device || '휠 상태 대기'}</p>
    {liveInput && <label>Live input <select value={useUdp?'udp':'direct'} onChange={e=>switchInput(e.target.value==='direct')}>
      <option value="udp">In-game UDP Actions</option><option value="direct">Direct wheel</option></select></label>}
    {useUdp ? <><p lang="ko">게임 휠 설정에서 아래 UDP Action에 버튼을 지정해.</p>
      {Object.entries(udpBindings).map(([key,action])=><div className="wheel-row" key={key}><b>UDP Action {key.slice(4)}</b><span>{action==='askCodex'?(mic?.enabled?'Radio microphone':'Request Codex plan'):labels[action]}</span></div>)}</>
    : <>{Object.entries(labels).map(([id,label])=>{const action=id as WheelAction;
      return <div key={id} className="wheel-row"><b>{label}</b>
        <span>{Object.entries(bindings).filter(([,a])=>a===action).map(([k])=>k.split('/').pop()).join(', ') || 'Unassigned'}</span>
        <button aria-label={'Bind '+label} onClick={()=>listen(action)}>Bind</button>
        <button aria-label={'Clear '+label} onClick={()=>clear(action)}>Clear</button></div>;})}
    <p lang="ko" role="status">{target ? labels[target]+' · 다이얼을 돌리거나 스틱을 눌러 입력' : feedback || 'Bind를 선택한 뒤 다이얼을 돌리거나 버튼을 한 번 눌러'}</p></>}
    </section><div className="settings-help"><details><summary>Keyboard shortcuts</summary>
      <dl>{Object.entries(shortcuts).map(([key,action])=><div key={key}><dt>{labels[action]}</dt>
        <dd><kbd>{key.replace('Arrow','').replace('Escape','Esc')}</kbd></dd></div>)}</dl>
    </details><details><summary>My Race controls</summary>
      <p lang="ko">위아래로 교체 일정을 확인하고 확정을 한 번 누르면 플랜이 적용돼. 실시간 주행 중에는 게임의 다음 타이어도 설정해.</p>
      <p lang="ko">Request Codex plan에서 확정을 누르면 전략 제안을 요청해. 주행 중에는 A/B/C가 갱신돼. 원하는 플랜 하나를 누르면 적용돼.</p>
    </details></div></div>}<button onClick={()=>ref.current?.close()}>Close</button></dialog>;
}

