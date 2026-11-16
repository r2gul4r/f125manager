import {teamBadgeStyle} from './teamBadgeStyle';
import type {Car} from './timing';

export function RankDriver({car, rank, title}: {car: Car; rank: number; title?:string}) {
  return <span className="rank-driver" title={title} style={teamBadgeStyle(car.color, car.retired)}>
    <span className="rank">{rank}</span>
    <span className="name-frame"><b>{car.code}</b></span>
  </span>;
}
