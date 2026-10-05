// Bounded presentation queue. Compressed decoding dependencies are never dropped.
class PtsPreview {
  constructor(draw, settings){this.draw=draw;this.settings=settings;this.frames=[];this.origin=null;this.lastPts=null;this.lastArrival=null;this.lastDraw=null;}
  reset(){for(const f of this.frames)f.close();this.frames=[];this.origin=null;this.lastPts=null;this.lastArrival=null;this.lastDraw=null;}
  push(frame,now,latestPts=frame.timestamp){
    if(!this.origin && latestPts-frame.timestamp>40000){frame.close();return;}
    if(this.lastPts!==null && frame.timestamp<=this.lastPts){frame.close();return;}
    if(this.lastArrival!==null && now-this.lastArrival>300)this.reset();
    this.lastPts=frame.timestamp;this.lastArrival=now;
    this.origin??={pts:frame.timestamp,now};this.frames.push(frame);
    if(this.frames.length>8 || frame.timestamp-this.origin.pts-(now-this.origin.now)*1000>300000){
      const newest=this.frames.pop();this.reset();this.frames.push(newest);this.lastPts=newest.timestamp;this.lastArrival=now;this.origin={pts:newest.timestamp,now};
    }
  }
  tick(now){
    if(!this.origin)return;
    const s=this.settings(),fps=s.preview_fps||30,delay=s.preview_buffer_ms??60;
    if(this.lastDraw!==null && now-this.lastDraw<1000/fps-1)return;
    const due=this.origin.pts+(now-this.origin.now-delay)*1000;
    let frame;
    while(this.frames.length && this.frames[0].timestamp<=due){if(frame)frame.close();frame=this.frames.shift();}
    if(!frame)return;
    try{this.draw(frame,now);}finally{frame.close();this.lastDraw=now;}
  }
}
if(typeof module!=='undefined')module.exports={PtsPreview};
