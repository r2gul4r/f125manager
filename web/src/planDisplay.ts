import type {Frame, RaceForecast, ServiceForecast, TyreExit} from './timing.ts';

const confirmExitMs = 2000;
const maxExitHoldMs = 4000;

interface DisplayedExit {
  row: TyreExit;
  service: ServiceForecast|null;
  lastMatch: number;
  candidate?: string;
  since: number;
}

// Publish one comparable A/B/C set per lap.
export class PlanDisplay {
  private context = '';
  private stock?:string;
  private published?: Pick<RaceForecast,'plans'|'recommended'|'cleanSamples'>;
  private exits: DisplayedExit[] = [];
  private exitContext = '';
  private lastSample = 0;

  update(frame:Frame|null, sampleMs=performance.now()):Frame|null {
    const me=frame?.cars[frame.player];
    if (!frame || !me || frame.mode!=='race' || me.retired) {
      this.context='';
      this.stock=undefined;
      this.published=undefined;
      this.exits=[];
      return frame;
    }
    const context=JSON.stringify([frame.session,frame.recordingHold,me.code,frame.lap,frame.flag,
      frame.weather.surface,frame.weather.rain,frame.weather.outlook?.map(x=>x.rain),
      me.pit,me.tyre,frame.advisor?.id,(frame.forecast ?? frame.previousPlans)?.plans.filter(p=>p.codexExpired).map(p=>p.id)]);
    const stock=frame.availableTyres?.slice().sort().join(',');
    if (context!==this.context || (stock!==undefined && stock!==this.stock)) {
      this.context=context;
      this.stock=stock;
      this.published=undefined;
      this.exits=[];
    }
    const forecast=frame.forecast;
    if (!forecast?.plans.length) {
      this.exits=[];
      return frame.previousPlans && this.published ?
        {...frame,previousPlans:{...frame.previousPlans,...this.published}} : frame;
    }
    this.published ??= {plans:forecast.plans,recommended:forecast.recommended,cleanSamples:forecast.cleanSamples};
    return {...frame,forecast:{...this.displayExits(frame,forecast,sampleMs),...this.published}};
  }

  private displayExits(frame:Frame,forecast:RaceForecast,now:number):RaceForecast {
    if (!forecast.tyreExits?.length) {
      this.exits=[];
      return forecast;
    }
    const context=JSON.stringify([frame.predictionLap ?? frame.lap,
      frame.cars.filter(car=>car.retired || car.pit).map(car=>[car.code,!!car.retired]).sort()]);
    if (context!==this.exitContext || now<this.lastSample || now-this.lastSample>maxExitHoldMs) this.exits=[];
    this.exitContext=context;
    this.lastSample=now;

    // Rank, gaps, traffic and service ranks must describe the same simulated exit.
    this.exits=forecast.tyreExits.map((row,offset)=>{
      const shown=this.exits[offset];
      const service=forecast.serviceRejoins?.[offset] ?? (offset===0 ? frame.serviceForecast ?? null : null);
      if (shown && (row.position!==shown.row.position || row.before!==shown.row.before || row.after!==shown.row.after)) {
        const candidate=JSON.stringify([row.position,row.before,row.after]);
        if (candidate!==shown.candidate) {
          shown.candidate=candidate;
          shown.since=now;
        }
        if (now-shown.since<confirmExitMs && now-shown.lastMatch<maxExitHoldMs) return shown;
      }
      return {row,service,lastMatch:now,since:now};
    });
    return {...forecast,tyreExits:this.exits.map(exit=>exit.row),serviceRejoins:this.exits.map(exit=>exit.service)};
  }
}
