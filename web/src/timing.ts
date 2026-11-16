export type SectorTimes = [number, number, number];
export type MiniSplit = 'normal' | 'personal' | 'fastest';

export interface PendingPenalty {
  kind: 'time' | 'drive_through' | 'stop_go';
  seconds: number;
}

export interface Car {
  code: string;
  color: string;
  position: number;
  change: number|null;
  pendingPenalties?: PendingPenalty[];
  gapMs: number|null;
  intervalMs: number|null;
  lastMs: number;
  bestMs: number;
  sectors: SectorTimes;
  personal: SectorTimes;
  tyre: Compound|null;
  age: number|null;
  stints?: {tyre:Compound|null; laps:number}[];
  minis?: (MiniSplit | 'pending')[];
  miniLastLap?: boolean;
  miniProgress?: number[] | null;
  sectorStatus?: (MiniSplit | 'pending')[];
  stintAge?:boolean; wheelWear?: number[] | null;
  liveSectors?: (number|null)[];
  speed: number|null;
  pit: boolean;
  retired?: boolean;
  world?:[number,number]|null;
  phase: number|null;
}

export interface RaceEvent {
  id: string;
  lap: number;
  driver: string;
  label: string;
  detail?: string;
  ruling?: 'black_white' | 'time' | 'drive_through' | 'stop_go';
  seconds?: number;
}

export interface UdpInfo {
  recordError?:string; recordDropped?:number; address:string; status:string; ageMs:number|null; format:number; accepted:number; rejected:number; error:string|null;
}
type ServiceEstimate = [rank:number, lossMs:number, samples:number];
export type ServiceForecast = [tyres:ServiceEstimate, frontWing:ServiceEstimate];
export interface PitComparison {lap:number; predicted:number|null; recalculated?:number|null; actual:number|null; entryMs:number; exitMs:number|null; serviceMs?:number; wingRepair?:boolean; penalty?:boolean; safety?:number; safetyChanged?:boolean; safetyStates?:number[]; serviceDelayed?:boolean|null; pitExperience?:number|null; serviceSafety?:number|null; serviceVerdict?:"normal"|"suspectedDelay"|"overlap"|"outsideProfile"|null; serviceIncluded?:boolean; lossIncluded?:boolean; measuredLossMs?:number|null; transitReferences?:number; tyreChanged?:boolean|null; repairs?:string[]; entryScenarios?:ServiceForecast|null; recordedScenarios?:ServiceForecast|null}
export interface Frame {
  microphoneMode?: boolean;
  recordingId?:string; raceFinished?:boolean;
  lastPitExit?:MeasuredExit|null;
  displayStamp?:{at:number;branch:number;tick:number};
  preRace?: {
    fieldLaps:number; playerLaps:number; inventoryKnown:boolean;
    tyres: Partial<Record<Compound,{paceMs:number; trendMs:number|null; pairs:number; source:string;
      trendSource:string; laps:number; wearPct:number|null; wearSource:string; wearLaps:number}>>;
    plans:(Plan & {modelMs:number})[];
  };
  advisor?: {available:boolean; pending:boolean; message:string; id?:string; reason?:string; plan?:Omit<ForecastPlan,'id'> | (Plan & {modelMs:number})};
  selectedPlan?: ForecastPlan["id"] | null; observedStints?: Stop[];
  recordingHold?: boolean;
  gameSync?: string;
  neutralPitLoss?:[number,number]|null;
  availableTyres?:Compound[]|null; fittedLife?:number|null;
  gamePitWindow?:[number,number]|null; gameRejoin?:number|null;
  lastRejoin?: [number,number]|null;
  pitLossMs?: number; pitLossSamples?: number; gamePitPriorMs?: number|null;
  serviceAverages?:([number,number]|null)[];
  serviceTimes?:([tyres:[number,number],wing:[number,number]]|null)[]|null;
  serviceForecast?:ServiceForecast|null;
  boxNowPosition?:number|null; predictionLap?:number; paused?:boolean; pitComparisons?:PitComparison[];
  isRace?:boolean; timeLeft?:number; source?: 'Live'|'Replay'; totalLaps?:number; sessionName?:string; trackId?:number; canPlan?:boolean;
  weather: RaceWeather;
  forecast?: RaceForecast | null;
  forecastWait?: string|null;
  previousPlans?: RaceForecast & {lap:number;startTyre?:Compound|null};
  paceHistory?: [number, number, string][];
  session: number|string;
  mode: 'grid' | 'race' | 'dnf';
  token: string;
  plan: Plan;
  notice: string;
  wheel: {device: string; keys: string[]; bindings: Record<string,string>};
  lapAnalysis?: {chase:Pace|null; defend:Pace|null};
  analysis: {
    chase: Pace | null; defend: Pace | null;
  };
  lap: number;
  scene: string;
  flag: string;
  yellowSectors?: number[];
  marshalZones?: [startFraction:number, flag:number][];
  player: number;
  events: RaceEvent[];
  cars: Car[];
}

export const compounds = {S:'Soft', M:'Medium', H:'Hard', I:'Intermediate', W:'Wet'};
export type Compound = keyof typeof compounds;
export interface RaceWeather {
  rain: 'Unknown'|'Light cloud'|'Overcast'|'Storm'|'Clear'|'Light rain'|'Heavy rain'|'Clearing';
  surface: 'Dry'|'Damp'|'Standing water'|'Unknown';
  condition: 'Dry'|'Wet'|'Unknown';
  approximate?:boolean;trackTemp?:number|null; airTemp?:number|null;
  outlook?:{minutes:number;rain:string;chance:number}[];
}
export interface ForecastPlan {
  codexReason?:string;
  codexExpired?:boolean;
  scenarioRanks?:number[];
  id: 'A'|'B'|'C'; stop: Stop; remainingMs: number; wearMs: number; wearObserved?: boolean; net: number;
  finish: [number, number]; risk: string; traffic: boolean; window: [number, number];
  lifeShortfall?:number; timeLeftMs?:number;
  wearRisk?:Record<number,{wearPct:number|null;excessPct:number|null}>;
  tyreIssues?:[firstLap:number,lastLap:number,tyre:Compound,reason:'life'|'stock'|'weather'][];
  stops?:Stop[];
}
export interface RaceForecast {
  partialLap?:boolean;
  inventoryKnown?:boolean;
  privateRivals?:number;
  plans: ForecastPlan[]; recommended: ForecastPlan['id']|null; cleanSamples: number; rejoins: Rejoin[];
  cutScenarios?:Partial<Record<Compound,[under:number,over:number,scenarios:number][]>>;
  trafficWindowMs?:number;
  cutRivals?:string[];
  tyreExits?:TyreExit[];
  serviceRejoins?:(ServiceForecast|null)[];
  rivals: Record<string, {probability: number[]; window: [number, number]|null; undercutMs: number; overcutMs: number}>;
}
export interface Stop {lap: number; tyre: Compound}
export interface Plan {start: Compound|null; stops: Stop[]}
export interface Pace {sampleLaps?:number;leader: string; follower: string; deltaMs: number; laps: number | null; lap: number; windowMs?:number|null; gapMs?:number;partialLap?:boolean}
export interface TyreExit extends Rejoin {entryPosition:number; aheadTrend?:GapTrend; behindTrend?:GapTrend;rivalMargins?:[string,number][];penaltyMs?:number;lapPaceMs?:[string,number][];validation?:[boolean,number,number|null,number|null]|null}
export type MeasuredExit = Pick<Rejoin,'position'|'before'|'after'|'aheadGapMs'|'behindGapMs'> & {waiting?:boolean};
export type GapTrend = "closing" | "opening" | "steady";
export interface Rejoin {aheadGapMs?:number|null; behindGapMs?:number|null; trafficAhead?:[string,number][]; position: number; before: string | null; after: string | null; lossMs: number}
export type Action = 'A' | 'B' | 'up' | 'down' | 'left' | 'right' | 'ok' | 'back';

export function sectorLeaders(cars: Car[]) {
  return [0, 1, 2].map(index =>
    cars.filter(c=>c.sectors[index]>0).sort((a, b) => a.sectors[index] - b.sectors[index] || a.position - b.position).slice(0, 4)
  );
}

export const EVENT_ROWS = 6;
export const EVENT_COLUMNS = 2;

export function visibleEvents(events: RaceEvent[]) {
  return events.slice(0, EVENT_ROWS * EVENT_COLUMNS).map((event, index) => ({
    event, column: Math.floor(index / EVENT_ROWS), row: index % EVENT_ROWS,
  }));
}
