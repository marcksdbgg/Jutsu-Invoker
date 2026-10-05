const {test}=require('node:test');const assert=require('node:assert/strict');
const {PtsPreview}=require('../src/jutsu_invoker/web/preview.js');
function frame(timestamp){return {timestamp,closed:0,close(){this.closed++;}};}
test('burst decoded frames are presented by capture timestamps with a 60ms buffer',()=>{
  const shown=[],q=new PtsPreview((f,t)=>shown.push([f.timestamp,t]),()=>({preview_fps:30,preview_buffer_ms:60}));
  const a=frame(1000000),b=frame(1033333),c=frame(1066666);q.push(a,0);q.push(b,0);q.push(c,0);
  q.tick(50);assert.deepEqual(shown,[]);q.tick(60);q.tick(94);q.tick(128);
  assert.deepEqual(shown.map(x=>x[0]),[a.timestamp,b.timestamp,c.timestamp]);assert.equal(a.closed,1);assert.equal(b.closed,1);assert.equal(c.closed,1);
});
test('late draws discard old decoded frames and close every resource',()=>{
  const shown=[],q=new PtsPreview(f=>shown.push(f.timestamp),()=>({preview_fps:30,preview_buffer_ms:0}));
  const frames=[frame(0),frame(33000),frame(66000)];frames.forEach(f=>q.push(f,0));q.tick(100);
  assert.deepEqual(shown,[66000]);assert.ok(frames.every(f=>f.closed===1));
});
test('queue stays bounded and a new camera session closes previous frames',()=>{
  const q=new PtsPreview(()=>{},()=>({})),frames=Array.from({length:30},(_,i)=>frame(i*33000));
  frames.forEach((f,i)=>q.push(f,i*33));assert.ok(q.frames.length<=8);q.reset();assert.ok(frames.every(f=>f.closed===1));
});
test('non-increasing PTS and gaps cannot replay old frames',()=>{
  const shown=[],q=new PtsPreview(f=>shown.push(f.timestamp),()=>({preview_buffer_ms:0}));
  const a=frame(1000),duplicate=frame(1000),old=frame(900);q.push(a,0);q.push(duplicate,1);q.push(old,2);q.tick(10);
  assert.equal(duplicate.closed,1);assert.equal(old.closed,1);const fresh=frame(401000);q.push(fresh,400);q.tick(400);assert.deepEqual(shown,[1000,401000]);
});

test('startup decodes may be old but only recent GOP output is presented',()=>{
  const shown=[],q=new PtsPreview(f=>shown.push(f.timestamp),()=>({preview_buffer_ms:0}));
  const old=frame(0),recent=frame(966667),latest=frame(1000000);
  q.push(old,0,1000000);q.push(recent,1,1000000);q.push(latest,2,1000000);q.tick(1);q.tick(35);
  assert.equal(old.closed,1);assert.deepEqual(shown,[966667,1000000]);assert.equal(latest.closed,1);
});
