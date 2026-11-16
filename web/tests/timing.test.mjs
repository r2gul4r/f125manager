import {test} from 'node:test';
import assert from 'node:assert/strict';
import {visibleEvents, sectorLeaders} from '../src/timing.ts';

test('events fill six rows down the left then down the right, shifting one slot per arrival', () => {
  const history = Array.from({length:21}, (_,i) => ({id:21-i}));
  const visible = visibleEvents(history);
  assert.deepEqual(visible.map(slot=>slot.event.id), history.slice(0,12).map(event=>event.id));
  assert.deepEqual(visible.map(({row,column})=>[row,column]),
    [0,1].flatMap(column=>Array.from({length:6}, (_,row)=>[row,column])));
  const shifted = visibleEvents([{id:22},...history]);
  assert.deepEqual(shifted.slice(1).map(s=>s.event), visible.slice(0,-1).map(s=>s.event));
  assert.deepEqual(shifted[6], {event:visible[5].event, column:1, row:0});
  assert.equal(visibleEvents(history.slice(0,2)).length, 2);
  assert.deepEqual(visibleEvents([]), []);
});

test('each sector takes its own four quickest times with stable ties', () => {
  const cars = [[3,1,5],[2,4,4],[1,2,3],[4,3,2],[4,5,1]]
    .map((sectors,i)=>({position:i+1, sectors}));
  assert.deepEqual(sectorLeaders(cars).map(group=>group.map(car=>car.position)), [
    [3,2,1,4], [1,3,4,2], [5,4,3,2]
  ]);
});
