const {test}=require('node:test');
const assert=require('node:assert/strict');
const {SealSoundCursor,SealSound}=require('../src/jutsu_invoker/web/sound.js');
const accepted=(t,token='Q')=>({type:'accepted',token,timestamp_ms:t,received_ms:t});
const loadedBuffers=()=>({monkey:{},tiger:{},horse:{},snake:{},confirm:{}});
test('never replay existing history when loading or polling again',()=>{
  const cursor=new SealSoundCursor();
  assert.deepEqual(cursor.consume([accepted(100)],110),[]);
  assert.deepEqual(cursor.consume([accepted(100)],120),[]);
  assert.equal(cursor.consume([accepted(100),accepted(130,'W')],140).length,1);
  assert.deepEqual(cursor.consume([accepted(130,'W')],150),[]);
});
test('all accepted seals and confirmed snake sound once; candidates/rejections do not',()=>{
  const cursor=new SealSoundCursor();cursor.consume([],0);
  const events=[accepted(10),accepted(20,'W'),accepted(30,'E'),{type:'recipe',spell:'Deafening Blast',timestamp_ms:40,received_ms:40},{type:'rejected',received_ms:50},{type:'cancelled',received_ms:60}];
  assert.equal(cursor.consume(events,70).length,4);
  assert.deepEqual(cursor.consume(events,80),[]);
});
test('ignore delayed events after suspension and future timestamps',()=>{
  const cursor=new SealSoundCursor();cursor.consume([],0);
  assert.deepEqual(cursor.consume([accepted(10),accepted(901),accepted(NaN)],900),[]);
  assert.deepEqual(cursor.consume([accepted(10)],901),[]);
  assert.equal(cursor.consume([accepted(902)],903).length,1);
});
test('muting or locked audio consumes events without replay on unmute',()=>{
  const sound=new SealSound();let plays=0;sound.play=()=>plays++;
  sound.consume([],0);sound.consume([accepted(10)],20);assert.equal(plays,0);
  sound.context={state:'running'};sound.buffers=loadedBuffers();sound.mute();sound.consume([accepted(10),accepted(30)],40);
  sound.enabled=true;sound.consume([accepted(30)],50);assert.equal(plays,0);
  sound.consume([accepted(60)],70);assert.equal(plays,1);
  sound.setVolume(0);sound.consume([accepted(80)],90);assert.equal(plays,1);
});
test('snake sounds its fourth tick but only an actual game cast sounds success',()=>{
  const sound=new SealSound();const plays=[];sound.play=kind=>plays.push(kind);
  sound.context={state:'running'};sound.buffers=loadedBuffers();sound.enabled=true;
  sound.consume([],0,true);
  sound.consume([accepted(10),{type:'recipe',spell:'Chaos Meteor',timestamp_ms:20,received_ms:20}],30,true);
  assert.deepEqual(plays,['monkey','snake']);
  sound.consume([{type:'cancelled',received_ms:35},{type:'sent_waiting_gsi',received_ms:40}],50,true);
  assert.deepEqual(plays,['monkey','snake']);
  const prepared={type:'prepared',spell:'Chaos Meteor',timestamp_ms:60,received_ms:60};
  sound.consume([prepared],70,true);sound.consume([prepared],80,true);
  assert.deepEqual(plays,['monkey','snake']);
  const cast={type:'cast',spell:'Chaos Meteor',timestamp_ms:90,received_ms:90};
  sound.consume([cast],100,true);sound.consume([cast],110,true);
  assert.deepEqual(plays,['monkey','snake','confirm']);
});
test('the local trainer plays snake without inventing a game cast',()=>{
  const sound=new SealSound();const plays=[];sound.play=kind=>plays.push(kind);
  sound.context={state:'running'};sound.buffers=loadedBuffers();sound.enabled=true;
  sound.consume([],0);sound.consume([{type:'recipe',spell:'EMP',timestamp_ms:10,received_ms:10}],20,false);
  assert.deepEqual(plays,['snake']);
});
test('each posture uses its own source tick regardless of recipe order',()=>{
  const sound=new SealSound();const plays=[];sound.play=kind=>plays.push(kind);
  sound.context={state:'running'};sound.buffers=loadedBuffers();sound.enabled=true;
  sound.consume([],0,true);
  sound.consume([accepted(10,'E'),accepted(20,'W'),accepted(30,'Q')],40,true);
  assert.deepEqual(plays,['horse','tiger','monkey']);
  sound.consume([accepted(10,'E'),accepted(20,'W'),accepted(30,'Q')],50,true);
  assert.equal(plays.length,3);
});
test('the same accepted event arriving by push and state polling sounds once',()=>{
  const cursor=new SealSoundCursor();cursor.consume([],0);
  assert.equal(cursor.consume([accepted(10)],20).length,1);
  assert.deepEqual(cursor.consume([{...accepted(10),received_ms:11}],30),[]);
});
