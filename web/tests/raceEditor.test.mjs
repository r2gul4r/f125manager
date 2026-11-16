import {test} from 'node:test';
import assert from 'node:assert/strict';
import {editPlan} from '../src/raceEditor.ts';
import {PlanDisplay} from '../src/planDisplay.ts';

const stops=[{lap:19,tyre:'S'},{lap:23,tyre:'H'}];
const plans=['A','B','C'].map(id=>({id,stop:stops[0],stops}));
const race={session:1,mode:'race',source:'Live',player:0,cars:[{code:'YOU',tyre:'M'}],lap:18,
  flag:'TRACK CLEAR',weather:{surface:'Dry'},plan:{start:'M',stops:[]},forecast:{recommended:'A',plans}};

test('rejoin labels wait for sustained changes per pit lap and keep matching gaps and service ranks',()=>{
  const display=new PlanDisplay();
  const row=(before,position,aheadGapMs)=>({before,after:'ALB',position,aheadGapMs});
  const first=row('GAS',4,700), changed=row('NOR',5,900);
  function update(now,near,far,extra={}) {
    const tyreExits=[near,far];
    const serviceRejoins=tyreExits.map(r=>[[r.position,14000,1],[r.position+2,19000,1]]);
    return display.update({...race,...extra,forecast:{...race.forecast,tyreExits,serviceRejoins}},now).forecast;
  }
  update(0,first,first);
  const live=row('GAS',4,580);
  assert.deepEqual(update(100,changed,live).tyreExits,[first,live]);
  assert.equal(update(200,first,first).tyreExits[0],first);
  update(300,changed,first);
  for (const now of [300,1800,2299]) {
    const held=update(now,changed,first);
    assert.equal(held.tyreExits[0],first);
    assert.equal(held.serviceRejoins[0][0][0],4);
  }
  const confirmed=update(2300,changed,first);
  assert.equal(confirmed.tyreExits[0],changed);
  assert.equal(confirmed.serviceRejoins[0][0][0],5);
  const third=row('PIA',6,1200);
  update(3000,first,first);
  update(4000,third,first);
  update(5000,first,first);
  update(6000,third,first);
  assert.equal(update(6300,first,first).tyreExits[0],first);
  assert.equal(update(3000,changed,first).tyreExits[0],changed);
  assert.equal(update(3100,third,first,{flag:'SC'}).tyreExits[0],third);
  assert.equal(update(3200,first,first,{flag:'SC',cars:[race.cars[0],{code:'GAS',pit:true}]}).tyreExits[0],first);
});

test('moving only previews; one press applies the displayed schedule',()=>{
  const preview=editPlan({cursor:0},'down',race);
  assert.equal(preview.confirm,undefined);
  const result=editPlan(preview.editor,'ok',race);
  assert.deepEqual(result.confirm,{start:'M',stops});
  assert.equal(result.replaceFuture,true);
  assert.equal(editPlan(preview.editor,'left',race).confirm,undefined);
  for(const frame of [{...race,forecast:null},{...race,canPlan:false},{...race,lap:20},{...race,availableTyres:['I']}])
    assert.equal(editPlan(preview.editor,'ok',frame).confirm,undefined);
});

test('grid FP plan and Codex actions remain reachable without an editor',()=>{
  const pre={start:'H',stops:[],modelMs:100};
  const frame={...race,mode:'grid',lap:0,preRace:{plans:[pre]},advisor:{available:true,plan:{}}};
  assert.deepEqual(editPlan({cursor:0},'ok',frame).confirm,{start:'H',stops:[]});
  assert.equal(editPlan({cursor:4},'ok',frame).advisor,'askCodex');
  assert.equal(editPlan({cursor:5},'ok',frame).advisor,'applyCodex');
});

test('expired row blocks confirmation and wheel skips it in both directions until renewal',()=>{
  const locked=plans.map(p=>({...p,codexExpired:p.id==='B'}));
  const frame={...race,forecast:{...race.forecast,plans:locked}};
  assert.equal(editPlan({cursor:1},'ok',frame).confirm,undefined);
  assert.equal(editPlan({cursor:0},'down',frame).editor.cursor,2);
  assert.equal(editPlan({cursor:2},'up',frame).editor.cursor,0);
  const display=new PlanDisplay();
  display.update(race);
  assert.equal(display.update(frame).forecast.plans[1].codexExpired,true);
  assert.deepEqual(editPlan({cursor:1},'ok',display.update(race)).confirm.stops,stops);
});

test('hold A/B/C within the lap while live pit estimates keep updating',()=>{
  const display=new PlanDisplay();
  display.update(race);
  const next={...race,forecast:{recommended:'C',plans:plans.slice().reverse(),rejoins:['new']}};
  const stable=display.update(next);
  assert.equal(stable.forecast.recommended,'A');
  assert.equal(stable.forecast.plans[0].id,'A');
  assert.deepEqual(stable.forecast.rejoins,['new']);
  const chosen=display.update({...next,selectedPlan:'B',plan:{start:'M',stops}});
  assert.equal(chosen.selectedPlan,'B');
  assert.equal(chosen.forecast.plans,stable.forecast.plans);
  assert.equal(chosen.forecast.recommended,stable.forecast.recommended);
  const held=display.update({...next,forecast:null,previousPlans:{...next.forecast,lap:18}});
  assert.equal(held.forecast,null);
  assert.equal(held.previousPlans.recommended,'A');
  for(const change of [{lap:19},{flag:'VSC'},{weather:{surface:'Wet'}},{availableTyres:['I']},{cars:[{code:'YOU',tyre:'H'}]},{session:2}]){
    const cache=new PlanDisplay();cache.update(race);
    assert.equal(cache.update({...next,...change}).forecast.recommended,'C');
  }
});
