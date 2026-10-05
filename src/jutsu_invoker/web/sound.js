/* Preloaded local Naruto effect excerpts. Sources: referencias/audio/PROVENANCE.md. */
class SealSoundCursor {
  constructor(){this.initialized=false;this.seen=new Set();}
  consume(events,now){
    const fresh=[];
    for(const event of events){
      if(!['accepted','recipe','cast'].includes(event.type))continue;
      const stamp=event.received_ms,key=[event.timestamp_ms??stamp,event.type,event.token||event.spell].join(':');
      if(this.seen.has(key))continue;
      this.seen.add(key);
      if(this.initialized && Number.isFinite(stamp) && now>=stamp && now-stamp<=700)fresh.push(event);
    }
    this.initialized=true;
    // Server history is bounded. Retain more identities than one history window.
    while(this.seen.size>256)this.seen.delete(this.seen.values().next().value);
    return fresh;
  }
}

class SealSound {
  constructor(onState=()=>{}){
    this.cursor=new SealSoundCursor();this.onState=onState;this.context=null;this.buffers={};this.loading=null;this.voice=null;
    this.enabled=this.read('jutsu-sound-enabled','true')!=='false';
    const saved=Number(this.read('jutsu-sound-volume','65'));
    this.volume=Number.isFinite(saved)?Math.max(0,Math.min(100,saved)):65;
  }
  read(key,fallback){try{return localStorage.getItem(key)??fallback;}catch{return fallback;}}
  save(key,value){try{localStorage.setItem(key,String(value));}catch{/* Keep controls usable without storage. */}}
  setVolume(value){this.volume=Math.max(0,Math.min(100,Number(value)||0));this.save('jutsu-sound-volume',this.volume);if(this.voice)this.voice.gain.gain.setTargetAtTime(this.volume/100*this.voice.level,this.context.currentTime,.005);this.onState();}
  mute(){this.enabled=false;this.save('jutsu-sound-enabled',false);if(this.voice)this.voice.source.stop();this.onState();}
  async unlock(){
    this.enabled=true;this.save('jutsu-sound-enabled',true);
    try{
      if(!this.context){
        const Audio=window.AudioContext||window.webkitAudioContext;
        if(!Audio)throw new Error('Este navegador no ofrece audio.');
        this.context=new Audio({latencyHint:'interactive'});
        this.context.onstatechange=()=>this.onState();
      }
      if(!this.loading)this.loading=Promise.all(['monkey','tiger','horse','snake','confirm'].map(async name=>{
        const response=await fetch('/audio/naruto-'+name+'.wav');
        if(!response.ok)throw new Error('No se pudo cargar el efecto de '+(name==='confirm'?'confirmación':'sello')+'.');
        this.buffers[name]=await this.context.decodeAudioData(await response.arrayBuffer());
      })).catch(error=>{this.loading=null;throw error;});
      // Resume is called directly from the trusted click, before awaiting a fetch.
      await Promise.all([this.context.resume(),this.loading]);
    }finally{this.onState();}
  }
  get active(){return this.enabled && this.context?.state==='running' && ['monkey','tiger','horse','snake','confirm'].every(name=>!!this.buffers[name]);}
  consume(events,now,dotaArmed=false){
    for(const event of this.cursor.consume(events,now)){
      // Every accepted pose has its tick. Only a game-observed cast gets the fifth.
      const kind=event.type==='cast' ? 'confirm' : event.type==='recipe' ? 'snake'
        : event.type==='accepted' ? {Q:'monkey',W:'tiger',E:'horse'}[event.token] : null;
      if(kind && this.active && this.volume>0)this.play(kind);
    }
  }
  play(kind='monkey'){
    if(!this.active||this.volume===0)return;
    const c=this.context,t=c.currentTime;
    if(this.voice){
      this.voice.gain.gain.cancelScheduledValues(t);
      this.voice.gain.gain.setTargetAtTime(0,t,.004);this.voice.source.stop(t+.02);
    }
    const source=c.createBufferSource(),gain=c.createGain();
    const level=.72;
    source.buffer=this.buffers[kind];gain.gain.value=this.volume/100*level;
    source.connect(gain);gain.connect(c.destination);
    const voice={source,gain,level};this.voice=voice;
    source.onended=()=>{source.disconnect();gain.disconnect();if(this.voice===voice)this.voice=null;};
    source.start(t);
  }
}
if(typeof module!=='undefined')module.exports={SealSoundCursor,SealSound};
