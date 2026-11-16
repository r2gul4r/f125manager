import {RankDriver} from './RankDriver';
import {useEffect, useRef, useState, type CSSProperties} from 'react';
import {EVENT_ROWS, EVENT_COLUMNS, visibleEvents, type RaceEvent, type Car} from './timing';

const flagSignals = new Map([
  ['옐로 플래그', 'yellow'],
  ['그린 플래그', 'green'],
  ['레드 플래그', 'red'],
]);

function ControlBadge({label}: {label: string}) {
  if (label === '세이프티카' || label === 'VSC 발령') {
    return <b className="control-badge safety-board" aria-hidden="true">
      {label === '세이프티카' ? 'SC' : 'VSC'}
    </b>;
  }
  const flag = flagSignals.get(label);
  if (!flag) return null;
  return <span className="control-badge flag-board" data-flag={flag} aria-hidden="true"/>;
}

function RulingBadge({event}: {event: RaceEvent}) {
  switch (event.ruling) {
    case 'black_white': return <i className="warning-flag" aria-hidden="true"/>;
    case 'time': return <b className="ruling-code">+{event.seconds}s</b>;
    case 'drive_through': return <b className="ruling-code">DT</b>;
    case 'stop_go': return <b className="ruling-code">S/G {event.seconds}s</b>;
    default: return null;
  }
}

export function EventLog({events, cars}: {events: RaceEvent[]; cars: Map<string, Car>}) {
  const newestId = events[0]?.id;
  const previousId = useRef(newestId);
  const [highlight, setHighlight] = useState<string>();
  useEffect(() => {
    const arrived = previousId.current !== undefined && newestId !== previousId.current;
    previousId.current = newestId;
    if (!arrived || !newestId) return;
    setHighlight(newestId);
    const timer = window.setTimeout(() => setHighlight(undefined), 1600);
    return () => window.clearTimeout(timer);
  }, [newestId]);
  const layout = {'--event-rows': EVENT_ROWS, '--event-columns': EVENT_COLUMNS} as CSSProperties;
  return <section className="event-log panel" aria-labelledby="event-title">
    <h2 id="event-title">Race Events</h2>
    <ol aria-label="Latest events first" style={layout}>
      {visibleEvents(events).map(({event, row, column}) => {
        const car = cars.get(event.driver);
        return <li key={event.id} data-event={event.id} data-column={column} className={event.id === highlight && event.id === newestId ? "new-event" : undefined}
          style={{transform: `translate(${column * 100}%, ${row * 100}%)`}}
          title={[`L${event.lap}`, event.driver, event.label, event.detail].filter(Boolean).join(" ")}>
          <div className="event-id">
            <small>L{event.lap}</small>
            {car ? <RankDriver car={car} rank={car.position} title={`Current position: P${car.position}`}/>
              : event.driver || <ControlBadge label={event.label}/>}
          </div>
          <div className="event-info" lang="ko">
            <span className="event-heading"><RulingBadge event={event}/>{event.label}</span>
            {event.detail && <p className="event-detail">{event.detail}</p>}
          </div>
        </li>;
      })}
    </ol>
  </section>;
}
