import type {Compound} from './timing';

// Scripted UI examples. These values are neither telemetry nor model output.
export interface DemoLap {
  lap:number; stint:number; tyre:Compound; sectors:number[]; condition:'Clean'|'Pit'|'SC';
  decision:string; forecast:number; position:number;
}
export interface DemoSession {gp:string; session:string; laps:DemoLap[]}

function session(gp:string, name:string, base:number, start:number, metres:number): DemoSession & {metres:number} {
  const race = name === 'Race';
  const laps = [660,290,0,810,460,180].map((offset,i):DemoLap => {
    const pit = i===3, neutral = race && i===4;
    const sectors = [Math.round(base*.325)+offset, Math.round(base*.427)+i*14,Math.round(base*.248)+i*31];
    if (pit) sectors[2]+=12000;
    if (neutral) sectors[1]+=6500;
    return {lap:start+i,stint:i<3?1:2,tyre:i<3?'M':'H',sectors,
      condition:pit?'Pit':neutral?'SC':'Clean',decision:pit?'Box · M → H':neutral?'Hold position':'Stay out',
      forecast:race?7:4,position:(race?7:4)+(pit?3:neutral?1:i===0?1:0)};
  });
  return {gp,session:name,metres,laps};
}
export const archive = [
  session('Japan','FP1',94500,3,5807),session('Japan','Race',93600,15,5807),
  session('Bahrain','FP1',95000,5,5412),session('Bahrain','Race',94100,17,5412),
];
export const lapTime = (lap:DemoLap) => lap.sectors.reduce((sum,ms)=>sum+ms,0);
export const channels = {
  Speed:{unit:'km/h',max:340,values:[185,270,315,212,128,201,249,177,104,191,280,310]},
  Throttle:{unit:'%',max:100,values:[68,100,100,14,29,88,100,22,32,95,100,100]},
  Brake:{unit:'%',max:100,values:[0,0,0,82,41,0,0,64,48,0,0,0]},
  ERS:{unit:'%',max:100,values:[72,70,65,66,70,68,63,64,68,65,61,59]},
  'Tyre temperature':{unit:'°C',max:120,values:[85,86,89,93,96,93,91,94,100,95,90,89]},
};
export type Channel = keyof typeof channels;
export function trace(channel:Channel, lap:DemoLap, record:DemoSession) {
  const profile=channels[channel];
  const variant=record.laps.indexOf(lap)+(record.gp==='Japan'?0:2);
  return profile.values.map((value,i)=>Math.max(0, Math.min(profile.max, value+((i+variant)%5-2)*2)));
}
