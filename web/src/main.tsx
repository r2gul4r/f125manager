import {useEffect, useRef, useState} from 'react';
import {Recordings, ReplayTools, type Playback} from './Recordings';
import {MyRace} from './MyRace';
import {PlanDisplay} from './planDisplay';
import {usePitRecording} from './usePitRecording';
import {PitReview} from './PitReview';
import {TyreBadge} from './TyreBadge';
import {canInteract,useRaceControls} from './useRaceControls';
import {screens, screenOrder} from './screens';
import {SessionAnalysis} from './WeekendPanels';
import {createRoot} from 'react-dom/client';
import {liveVenue, suzuka, venues} from './circuits';
import {RankDriver} from './RankDriver';
import {WorldMap} from './WorldMap';
import {getTrackInfo} from './vendor/constants/f1';
import {Circuit} from './Circuit';
import {EventLog} from './EventLog';
import {formatGap, formatLapTime, formatSectorTime} from './vendor/utils/formatters';
import {sectorLeaders, type Car, type Frame, type UdpInfo} from './timing';
import './screen.css';
import './analysis.css';

const demoMode = new URLSearchParams(location.search).get('source')==='demo';
const replayId = new URLSearchParams(location.search).get('replay');
function useTiming() {
  const [playback,setPlayback]=useState<Playback|null>(null);
  const [idleKeys,setIdleKeys]=useState<string[]>([]);
  const [error,setError]=useState('');
  const [udp,setUdp]=useState<UdpInfo|null>(null);
  const pendingSeek = useRef<number|null>(null);
  const connection = useRef<WebSocket|null>(null);
  const planDisplay=useRef<PlanDisplay|null>(null);
  const [frame, setFrame] = useState<Frame | null>(null);
  const [status, setStatus] = useState('Connecting');
  useEffect(() => {
    let stopped = false;
    let socket: WebSocket;
    let retry: ReturnType<typeof setTimeout>;
    let lastReceived = 0;
    function connect() {
      pendingSeek.current=null;
      planDisplay.current=new PlanDisplay();
      socket = new WebSocket(location.origin.replace(/^http/, 'ws') + (replayId ? '/ws/replay/'+encodeURIComponent(replayId) : demoMode ? '/ws/demo' : '/ws/live'));
      connection.current = socket;
      let failed=false;
      let accepted:number|undefined;
      let telemetryMs=performance.now();
      socket.onmessage = e => {
        if (stopped) return;
        const data = JSON.parse(e.data);
        if (data.playback) {
          if (pendingSeek.current!==null && data.playback.ms!==pendingSeek.current) return;
          pendingSeek.current=null;
          setPlayback(data.playback);
        }
        if (!data.frame && data.wheelKeys?.length) setIdleKeys(data.wheelKeys);
        if (data.error){failed=true;clearInterval(timer);setError(data.error);}
        if (demoMode && !replayId) {setFrame(planDisplay.current!.update(data)); setStatus('Demo');}
        else {
          if (data.udp?.accepted!==accepted) {
            accepted=data.udp?.accepted;
            telemetryMs=performance.now();
          }
          const frame=data.status==='Last recording' && data.frame ? {...data.frame,recordingHold:true} : data.frame;
          setFrame(planDisplay.current!.update(frame,data.playback?.ms ?? telemetryMs));
          setStatus(data.status);
          setUdp(data.udp);
        }
        lastReceived = Date.now();
      };
      socket.onclose = () => {
        if (stopped || failed) return;
        lastReceived = 0;
        setStatus('Reconnecting');
        retry = setTimeout(connect, 1000);
      };
    }
    connect();
    const timer = setInterval(() => {
      if (lastReceived && Date.now()-lastReceived > 2000) setStatus('Stale data');
    }, 1000);
    return () => {stopped = true; clearTimeout(retry); clearInterval(timer); socket.close();};
  }, []);
  function send(data:object) {
    if (connection.current?.readyState !== WebSocket.OPEN) return false;
    if ('type' in data && data.type==='playback' && 'ms' in data && typeof data.ms==='number') {
      const ms=data.ms;
      pendingSeek.current='speed' in data && data.speed===0 ? data.ms : null;
      setPlayback(current=>current && {...current,ms,speed:0});
      planDisplay.current=new PlanDisplay();
    }
    connection.current.send(JSON.stringify(data));
    return true;
  }
  return {frame, status, send,udp,playback,idleKeys,error};
}

function SectorBoard({leaders}: {leaders: Car[][]}) {
  return <section className="sectors panel" aria-label="Last lap sector rankings">
    {leaders.map((cars, sector) => <div key={sector}><h2>S{sector+1}</h2>
      <ol>{cars.map((car, i) => <li key={car.code}><RankDriver car={car} rank={i+1}/>
        <span>{formatSectorTime(car.sectors[sector], false)}</span></li>)}</ol>
    </div>)}
  </section>;
}

const headings = ['DRIVER','±','LAST LAP','BEST LAP','INT','GAP','Sector 1','Sector 2','Sector 3','Tyre history','km/h'];

function TyreHistory({car}: {car:Car}) {
  const stints = car.stints ?? [{tyre:car.tyre, laps:car.age}];
  return <div className="tyre-history" title={stints.map(s=>s.laps+' laps · '+s.tyre).join(' → ')}>
    {Array.from({length:Math.max(3,stints.length)},(_,i)=>{
      const stint = stints[i];
      return <span className="tyres" key={i} data-empty={!stint || undefined}
        aria-label={stint ? `Stint ${i+1}: ${stint.laps} laps, ${stint.tyre}` : undefined} aria-hidden={!stint}>
        <small>{stint?.laps ?? 0}</small><TyreBadge compound={stint?.tyre}/>
      </span>;
    })}
  </div>;
}

function SectorCell({car,index}: {car:Car; index:number}) {
  const time = car.liveSectors?.[index];
  const splits = car.minis?.slice(index*8,(index+1)*8) ?? [];
  const progress=car.miniProgress?.[index];
  const miniLabel=demoMode?'Demo mini-sectors':(car.miniLastLap?'Last lap':'Current lap')+' · UDP split estimates · purple: field best · green: personal best · yellow: completed · grey: unmeasured';
  const status = demoMode ? (splits.length===8 && splits.every(s=>s==='fastest')?'fastest':
    splits.length===8 && splits.every(s=>s!=='normal')?'personal':'normal') : car.sectorStatus?.[index];
  return <td className="live-sector" title={miniLabel}>
    <span className={status==='fastest'?'purple':status==='personal'?'gain':status==='normal'?'yellow':'muted'}>{time ? formatSectorTime(time,false) : '—'}</span>
    {(demoMode || progress!=null) && <div className="mini-strip" aria-label={`Sector ${index+1}: ${demoMode?splits.length:splits.filter(s=>s!=='pending').length} of 8`}>
      {Array.from({length:8},(_,i)=><i key={i} data-split={splits[i] ?? (i<(progress??0)?'distance':'pending')}/>)}
    </div>}</td>;
}

function TimingTable({cars, player, selected, onSelect}: {
  cars: Car[]; player:string; selected:string; onSelect:(code:string)=>void;
}) {
  const fastest = Math.min(...cars.filter(c=>c.bestMs>0).map(car => car.bestMs));
  return <section className="tower panel" aria-label="Live Timing">
    <table aria-label="Driver standings"><colgroup><col className="driver-column"/>{[3.6,9.8,9.8,7.4,7.8,8.4,8.4,8.4,14,4.2].map((width,i) =>
      <col key={i} style={{width:width+'%'}}/>)}</colgroup>
      <thead><tr>{headings.map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead>
      <tbody>{cars.map(car => <tr key={car.code} data-driver={car.code} className={[
        car.code===player?'player':'', car.code===selected?'selected':''
      ].join(' ')} onClick={()=>onSelect(car.code)}>
        <td><div className="driver-cell">
          <button className="driver-select" aria-label={'Select '+car.code}
            aria-pressed={car.code===selected} onClick={e=>{e.stopPropagation();onSelect(car.code);}}>
            <RankDriver car={car} rank={car.position}/>
          </button>
          {!!car.pendingPenalties?.length && <small className="driver-penalties" title={car.pendingPenalties.map(p=>p.kind==='time'?`+${p.seconds}s`:p.kind==='drive_through'?'Drive-through':'Stop-go').join(' · ')}>
            {car.pendingPenalties.map(p=>p.kind==='time'?`+${p.seconds}s`:p.kind==='drive_through'?'DT':'SG').join(' · ')}
          </small>}
        </div></td>
        <td className={(car.change ?? 0)>0?'gain':(car.change ?? 0)<0?'loss':'muted'}>{(car.change ?? 0)>0?'▴':(car.change ?? 0)<0?'▾':'–'} {car.change==null?'':Math.abs(car.change)}</td>
        <td className={car.lastMs>0 && car.lastMs===car.bestMs?'gain':''}>{formatLapTime(car.lastMs)}</td>
        <td><span className={car.bestMs===fastest?'fastest':''}>{formatLapTime(car.bestMs)}</span></td>
        <td>{car.position===1 || car.intervalMs==null?'—':'+'+formatGap(car.intervalMs)}</td><td>{car.position===1 || car.gapMs==null?'—':'+'+formatGap(car.gapMs)}</td>
        {[0,1,2].map(i=><SectorCell key={i} car={car} index={i}/>)}
        <td><TyreHistory car={car}/></td>
        <td>{car.retired ? <strong aria-label="Retired">DNF</strong> : car.pit?<strong className="pit">PIT</strong>:car.speed ?? '—'}</td>
      </tr>)}</tbody>
    </table>
  </section>;
}

function TimingScreen() {
  const [venue, setVenue] = useState(suzuka);
  const {frame, status, send,udp,playback,idleKeys,error} = useTiming();
  const ready = canInteract(status);
  const controls = useRaceControls(frame,status,send,udp,idleKeys,!!replayId);
  usePitRecording(frame,status,controls.tab,controls.editor.cursor);
  const resultRecording = frame?.isRace && (frame.raceFinished || playback && playback.ms===playback.duration)
    ? replayId ?? frame.recordingId : null;
  const [selection, setSelection] = useState<string | null>(null);
  const cars = frame ? [...frame.cars].sort((a,b)=>a.position-b.position) : [];
  const player = frame?.cars[frame.player];
  const track = demoMode ? venue : liveVenue(frame?.trackId ?? -1);
  const selected = cars.find(car=>car.code===selection) ?? player ?? cars[0];
  const leaders = sectorLeaders(cars);
  return <><header>
    <div className="session"><strong>F1 25</strong><h1>{demoMode ? <select aria-label="Demo circuit" value={venue.id}
      onChange={e=>setVenue(venues.find(v=>v.id===e.target.value)!)}>
      {venues.map(v=><option key={v.id} value={v.id}>R{v.round} · {v.officialName}</option>)}
    </select> : track?.officialName ?? getTrackInfo(frame?.trackId)?.name ?? (frame ? "Track "+frame.trackId : "Game UDP")}</h1><b>{frame?.sessionName ?? (demoMode ? "Race" : "")}</b><small role="status">{status}</small></div>
    <nav aria-label="Race screens">{screenOrder.map(tab=><button key={tab}
      aria-current={controls.tab===tab?'page':undefined} onClick={()=>controls.navigate(tab)}>
      {screens[tab]}</button>)}</nav>
    <div className="race-state"><b>LAP {frame?.lap??'–'} {frame?.isRace===false ? ' · '+Math.floor((frame.timeLeft??0)/60)+':'+String((frame.timeLeft??0)%60).padStart(2,'0') : '/ '+(frame?.totalLaps ?? (demoMode?27:'–'))}</b><strong data-flag={frame?.flag} className={frame?.flag==='RED'?'red-flag':frame?.flag==='TRACK CLEAR'?'clear':'caution'}>{frame?.flag??'Waiting'}{frame?.flag==='YELLOW' && !frame.marshalZones && frame.yellowSectors?.map(s=>' S'+s).join('')}</strong>
      <button type="button" className="header-refresh" aria-label="새로고침" title="새로고침" onClick={() => window.location.reload()}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M20 5v5h-5M20 10a8 8 0 1 0 0 5"/>
        </svg>
      </button>
      <button id="race-menu-button" className="header-menu" popoverTarget="race-menu">Menu</button>
      <div id="race-menu" popover="auto">
      <button aria-haspopup="dialog" onClick={e=>{
        e.currentTarget.parentElement?.hidePopover();
        controls.openSettings();
      }}>Settings</button></div>
    </div>
  </header>
  {replayId && <ReplayTools state={playback} send={send}/>}
  {controls.tab==='analysis' ? <main className="tool-screen" aria-label={screens[controls.tab]}>
    <div className="work-panel"><div className="panel-heading"><h2>{screens[controls.tab]}</h2></div>
      {demoMode ? <SessionAnalysis/> : <Recordings initialRecording={replayId ?? resultRecording ?? null}/>}
    </div>
  </main> : controls.tab==='B' && resultRecording ? <main className="tool-screen"><div className="work-panel"><PitReview key={resultRecording} recording={resultRecording}
    expectedStops={frame?.pitComparisons?.filter(s=>s.exitMs!=null).length}/></div></main>
  : frame && selected ? controls.tab==='B' ? player ? <MyRace frame={frame} cars={cars} ready={ready} {...controls}/> : <p lang="ko">플레이어 차량 대기 · 관전 중에는 순위표 사용</p> : <main>
    <TimingTable cars={cars} player={player?.code ?? ''} selected={selected.code} onSelect={setSelection}/>
    <aside>{track ? <Circuit key={`${frame.session}-${frame.trackId ?? track.id}`} venue={track} flag={frame.flag} yellowSectors={frame.yellowSectors} marshalZones={frame.source==='Live' ? frame.marshalZones ?? [] : frame.marshalZones} cars={frame.cars.filter(c=>c.phase!=null)} lap={frame.lap} selected={selected}/> : <WorldMap key={String(frame.session)} cars={cars} selected={selected.code}/>}<SectorBoard leaders={leaders}/>
      <EventLog events={frame.events} cars={new Map(cars.map(car=>[car.code,car]))}/></aside>
  </main> : <p lang="ko" role="status">{error || (replayId ? (playback ? '이 재생 시점에 기록된 차량 타이밍 없음' : '녹화본 여는 중') : udp?.error || (demoMode?'경기 데이터 대기 중':(udp?.address ?? '127.0.0.1:20777')+' · 게임 텔레메트리 대기 중'))}</p>}{controls.dialog}
  </>;
}

createRoot(document.getElementById('root')!).render(<TimingScreen/>);
