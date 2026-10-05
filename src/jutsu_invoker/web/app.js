const el = id => document.getElementById(id);
const token = document.querySelector('meta[name=session-token]').content;
const names = {monkey:'Mono',tiger:'Tigre',horse:'Caballo',snake:'Serpiente',unknown:'Sin sello',transition:'Transición',evaluation:'Evaluación guiada'};
let soundStateSeen=false;
const reasons = {low_confidence_or_margin:'La imagen todavía es ambigua. Mantén el sello dentro del encuadre.',unsupported_or_transition:'Forma mono, tigre o caballo. Serpiente confirma la receta.',confirmation_without_recipe:'Serpiente necesita una receta pendiente. Empieza con un elemento.',selector_already_selected:'Ese elemento ya está guardado. Continúa con otro sello o confirma con serpiente.',recipe_timeout:'La receta caducó. Empieza otra receta.',settings_changed:'Ajustes actualizados. Empieza una receta nueva.',observation_gap:'La imagen saltó. Mantén la pose; tus sellos siguen guardados durante el plazo de reinicio.',stale_or_nonvisual:'Imagen atrasada descartada. Tus sellos siguen guardados durante el plazo de reinicio.',camera_session_changed:'Nueva sesión de cámara.',camera_stopped:'Cámara detenida.',manual_cancel:'Receta cancelada.',dota_context_changed:'Cambió la disponibilidad de Dota. Empieza una receta nueva.',camera_or_gpu_error:'Se interrumpió el reconocedor.'};
let evalModeRestored = false, jointsEnabled = localStorage.getItem('jutsu-joints-visible')==='true', videoPts = null, videoSeenAt = 0;
let settingsDirty=false, settingsSignature=null, tokensSignature=null, historySignature=null;
let frameIntervals=[], lastPreviewFrameAt=null, previewMeasureAt=null, previewFrames=0;
function notePreviewFrame(now){
  if(lastPreviewFrameAt!==null)frameIntervals.push(now-lastPreviewFrameAt);
  lastPreviewFrameAt=now;previewMeasureAt??=now;previewFrames++;
  if(now-previewMeasureAt>=1000){
    const sorted=frameIntervals.slice().sort((a,b)=>a-b), fps=previewFrames*1000/(now-previewMeasureAt),p95=sorted[Math.floor((sorted.length-1)*.95)]||0;
    const metric=el('preview-timing');metric.textContent=fps.toFixed(1)+' FPS · intervalo p95 '+p95.toFixed(1)+' ms';metric.dataset.fps=fps;metric.dataset.p95=p95;metric.dataset.min=sorted[0]||0;metric.dataset.max=sorted.at(-1)||0;
    frameIntervals=[];previewMeasureAt=now;previewFrames=0;
  }
}
let state = {}, recipes = [], previewEnabled = true, previewTask = null, videoAbort = null, busy = false, lastRecipe = null, nextPreviewAt = 0;

async function control(action, payload={}) {
  if (busy) return;
  busy = true;
  try {
    const response = await fetch('/api/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Jutsu-Token':token},body:JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    render(data);
    if(action==='evaluation/start')document.querySelector('.viewfinder').scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
    el('service-error').textContent = '';
  } catch(error) { el('service-error').textContent = error.message; }
  finally { busy = false; }
}

function pendingSpell(pending) {
  const orbs = pending.length===1 ? pending[0].repeat(3) : pending.length===2 ? pending[0].repeat(2)+pending[1] : pending.length===3 ? 'QWE' : '';
  const key = orbs.split('').sort().join('');
  return recipes.find(r=>r.orbs.split('').sort().join('')===key);
}

function render(data) {
  const audioEvents=[...(data.events||[]),...(data.dota?.cast_events||[])];
  if(!soundStateSeen){sealSound.cursor.consume(audioEvents,Infinity);soundStateSeen=true;}
  else sealSound.consume(audioEvents,data.server_monotonic_ms,!!data.dota?.armed);
  state = data;
  renderSettings(data);
  reasons.recipe_timeout='Pasaron '+(data.settings?.timeout_ms/1000||data.thresholds?.timeout_ms/1000||1.6)+' s sin reconocer un elemento guardado ni aceptar uno nuevo. Empieza otra receta.';
  el('evaluation-note').textContent='Mantén cada sello hasta ver su letra. Tienes '+(data.settings?.timeout_ms/1000||1.6)+' s para cambiar de pose sin evidencia del elemento guardado. Serpiente confirma tras '+(data.thresholds?.confirmation_stable_ms||200)+' ms estables y su mínimo de imágenes. 3,5 s para preparar cada intento. Los datos quedan en este PC.';
  renderEvaluation(data.evaluation || {status:'idle'});
  renderDota(data.dota || {});
  el('connection').textContent = {running:'Cámara activa',starting:'Preparando cámara…',stopped:'Cámara detenida',error:'Conexión interrumpida'}[data.status] || 'Conectando…';
  document.querySelector('.connection').dataset.status = data.status;
  el('camera').value = data.facing;
  el('camera-toggle').textContent = ['running','starting'].includes(data.status) ? 'Detener cámara' : 'Iniciar cámara';
  el('camera-toggle').disabled = data.status==='starting';
  el('reconnect').disabled = data.status==='starting';
  const signName=names[data.sign] || 'Sin sello';
  el('sign').textContent = ['monkey','tiger','horse','snake'].includes(data.sign)?signName+(data.accepted_sign===data.sign?' · aceptado':' · candidato'):signName;
  el('score').textContent = data.frames ? Number(data.score).toFixed(2) : '—';
  el('fps').textContent = data.fps ? data.fps.toFixed(1) : '—';
  el('processing').textContent = data.processing_ms ? data.processing_ms.toFixed(1)+' ms' : '—';
  el('margin').textContent=data.frames ? Number(data.margin).toFixed(2)+' · mínimo '+data.thresholds.class_margin.toFixed(2) : '—';
  el('backend').textContent = data.backend==='tensorrt' ? 'TensorRT · CUDA' : 'ONNX Runtime · CUDA';
  el('age').textContent = data.queue_age_ms!==undefined ? data.queue_age_ms.toFixed(1)+' ms' : '—';
  el('p95').textContent = data.processing_p95_ms ? data.processing_p95_ms.toFixed(1)+' ms' : '—';
  el('cpu').textContent = data.cpu_logical_threads!==undefined ? data.cpu_logical_threads.toFixed(2)+' hilos lógicos' : '—';
  el('rejection').textContent = reasons[data.rejection] || data.rejection || 'Ninguno';
  el('camera-mode').textContent = 'HONOR · '+(data.facing==='front'?'frontal':'trasera')+(data.dimensions ? ' · '+data.dimensions.join('×') : '')+(data.capture_orientation_degrees?' · giro '+data.capture_orientation_degrees+'°':'');
  drawJoints();
  const pending = data.pending || [];
  const nextTokens=JSON.stringify(pending);
  if(nextTokens!==tokensSignature){
    tokensSignature=nextTokens;el('tokens').replaceChildren();
    if (!pending.length) {
      const span = document.createElement('span');span.className='empty';span.textContent='Esperando el primer sello';el('tokens').append(span);
    } else for(const orb of pending) {
      const b = document.createElement('b');b.textContent=orb;b.className={Q:'quas',W:'wex',E:'exort'}[orb];el('tokens').append(b);
    }
  }
  const target = pendingSpell(pending);
  el('pending-spell').textContent = target ? target.name+' · serpiente para confirmar' : 'El primer sello decide el predominio.';
  if(pending.length && data.sign==='unknown')el('pending-spell').textContent=(target?.name||'Receta pendiente')+' · cambia de pose · '+(data.transition_remaining_ms/1000).toFixed(1)+' s restantes';
  el('feedback').textContent = data.error ? data.error+' Pulsa Reconectar.' : data.status!=='running' ? data.message : reasons[data.rejection] || 'Mantén el sello un instante y pasa al siguiente.';
  if(data.status==='running' && pending.length && ['unsupported_or_transition','low_confidence_or_margin'].includes(data.rejection))el('feedback').textContent='Puedes cambiar de pose: la receta se conserva · '+(data.transition_remaining_ms/1000).toFixed(1)+' s sin evidencia del elemento guardado.';
  const otherSeal=data.detections?.[0];
  const originalNames={'Hitsuji(Ram)':'carnero','Ne(Rat)':'rata','Tori(Bird)':'pájaro','I(Boar)':'jabalí','Inu(Dog)':'perro','Tatsu(Dragon)':'dragón','U(Hare)':'liebre','Ushi(Ox)':'buey'};
  if(data.status==='running' && data.sign==='unknown' && !pending.length && otherSeal?.sign==='unknown' && otherSeal.score>=.5 && originalNames[otherSeal.source_label])el('feedback').textContent='El modelo ve '+originalNames[otherSeal.source_label]+'. Compara tu pose con el dibujo; este sello se rechaza.';
  if(data.tiger_refinement?.accepted && data.status==='running' && data.accepted_sign!=='tiger')el('feedback').textContent='Candidato a tigre. Mantén la pose hasta ver W en tu receta.';
  if(data.last_recipe) {
    el('spell').textContent=data.last_recipe.spell;
    el('spell-orbs').textContent=data.last_recipe.orbs+' · confirmado con serpiente';
    if(lastRecipe!==data.last_recipe.timestamp_ms) {
      const result=document.querySelector('.result');result.classList.remove('confirmed');requestAnimationFrame(()=>result.classList.add('confirmed'));lastRecipe=data.last_recipe.timestamp_ms;
    }
  }
  if(!data.last_recipe){el('spell').textContent='Todavía ninguna';el('spell-orbs').textContent='La confirmación aparecerá aquí.';lastRecipe=null;}
  el('record-toggle').textContent=data.recording?'Terminar toma':'Grabar toma';
  el('record-toggle').disabled=data.status!=='running' || data.evaluation?.status==='running';
  el('record-label').disabled=!!data.recording;
  el('record-status').textContent=data.recording?'Grabando '+names[data.recording.label]+': '+data.recording.path : data.last_recording ? 'Toma guardada: '+data.last_recording.split('/').pop() : 'Sin grabación activa.';
  const events=[...(data.events||[])].reverse().slice(0,8), nextHistory=JSON.stringify(events);
  if(nextHistory!==historySignature){
    historySignature=nextHistory;el('history').replaceChildren();
    for(const event of events) {
      const li=document.createElement('li'),text=document.createElement('span'),time=document.createElement('time');
      text.textContent=event.type==='accepted'?names[event.sign]+' · '+event.token:event.type==='recipe'?event.spell:reasons[event.reason]||'Receta cancelada';
      time.dataset.receivedMs=event.received_ms;li.append(text,time);el('history').append(li);
    }
    if(!events.length){const li=document.createElement('li');li.className='empty';li.textContent='Los sellos aceptados aparecerán aquí.';el('history').append(li);}
  }
  for(const time of el('history').querySelectorAll('time')){
    const elapsed=Math.max(0,Math.round((data.server_monotonic_ms-Number(time.dataset.receivedMs))/1000)),label=elapsed<2?'Ahora':'Hace '+elapsed+' s';
    if(time.textContent!==label)time.textContent=label;
  }
  if(previewEnabled && !document.hidden && data.status==='running' && !previewTask && Date.now()>=nextPreviewAt) startPreview();
  if(data.status==='stopped' || data.status==='error') {
    stopPreview();el('video-message').hidden=false;el('video-message').textContent=data.status==='error'?'La cámara se interrumpió. Pulsa Reconectar.':'Cámara detenida. Pulsa Iniciar cámara.';
  }
}

function renderEvaluation(e) {
  const active=e.status==='running', report=e.report;
  if(!evalModeRestored && e.mode){el('eval-mode').value=e.mode;evalModeRestored=true;}
  el('evaluation-start').disabled=active || !['running'].includes(state.status);
  el('eval-mode').disabled=active;el('eval-rounds').disabled=active || el('eval-mode').value==='recipes';
  el('evaluation-exclude').hidden=!active;el('evaluation-abort').hidden=!active;
  el('evaluation-confirm').hidden=e.status!=='finished' || !!report?.user_confirmed_execution;
  el('trial-overlay').hidden=!active;
  if(active && e.target !== undefined) {
    const target=e.mode==='signs' ? names[e.target] : e.target.name+' · '+e.target.compact.map(t=>({Q:'Mono',W:'Tigre',E:'Caballo',R:'Serpiente'})[t]).join(' → ');
    let prompt=e.phase==='rest' ? 'Baja las manos. El siguiente intento empieza enseguida.' : e.phase==='prepare' ? 'Prepara: '+target : e.mode==='signs' ? 'Mantén: '+target : 'Haz la receta: '+target;
    if(el('eval-prompt').textContent!==prompt)el('eval-prompt').textContent=prompt;
    el('eval-countdown').textContent=Math.ceil(e.remaining_ms/1000)+' s';
    el('trial-prompt').textContent=prompt;el('trial-countdown').textContent=Math.ceil(e.remaining_ms/1000)+' s · '+e.trial+'/'+e.total;
    let guideSign=e.mode==='signs' && e.phase!=='rest' ? e.target : 'unknown';
    if(e.mode==='recipes' && e.phase!=='rest') {
      const signs={Q:'monkey',W:'tiger',E:'horse',R:'snake'}, sequence=e.target.compact;
      const pending=state.pending||[];
      const matches=pending.every((v,i)=>v===sequence[i]);
      const next=e.phase==='prepare' ? sequence[0] : matches ? sequence[pending.length] : sequence[0];
      guideSign=signs[next]||'unknown';
      const event=e.recipe_events?.[0];
      if(event){prompt=(event.spell===e.target.name?'Confirmado: ':'Se reconoció otra receta: ')+event.spell+'. Baja las manos y espera.';guideSign='unknown';}
      else prompt=(e.phase==='prepare'?'Prepara: ':'Siguiente sello: ')+(names[guideSign]||'')+' · '+target+(matches?'':' · secuencia distinta; empieza otra vez');
      el('eval-prompt').textContent=prompt;el('trial-prompt').textContent=prompt;
    }
    el('trial-reference').dataset.sign=guideSign;
    el('eval-progress').textContent='Intento '+e.trial+' de '+e.total+(e.excluded?' · excluido':'');
    el('eval-result').textContent=e.mode==='recipes'?'Sigue el siguiente dibujo. Haz una sola receta por intento; después baja las manos. No se envían teclas.':'Resultados al terminar. No se envían teclas durante la evaluación.';
  } else {
    el('eval-countdown').textContent='';el('eval-progress').textContent='';
    el('eval-prompt').textContent=e.status==='finished'?'Prueba terminada. Revisa los resultados y confirma si hiciste los gestos indicados.':e.status==='aborted'?'Prueba detenida. Los datos parciales se conservaron.':'Coloca ambas manos dentro del encuadre. El piloto te indicará qué sello hacer.';
    if(report) {
      const pct=report.trial_accuracy===null?'sin datos suficientes':(100*report.trial_accuracy).toFixed(1)+'%';
      let text=(report.provisional?'Provisional · ':'Etiquetas confirmadas por ti · ')+report.correct_trials+'/'+report.included_trials+' intentos correctos ('+pct+'). '+(report.total_trials-report.included_trials)+' no evaluables.\n';
      if(report.mode==='signs') {
        for(const sign of ['monkey','tiger','horse','snake','unknown']) {
          const trials=report.trials.filter(t=>t.expected===sign && t.included);
          text+=names[sign]+': '+trials.filter(t=>t.correct).length+'/'+trials.length+' · ';
        }
      }
      text+='\nInforme: '+e.report_path+'\nPiloto de esta sesión; no prueba precisión en sesiones nuevas.';
      el('eval-result').textContent=text;
    } else el('eval-result').textContent='';
  }
}

function renderDota(d) {
  el('dota-arm').disabled=!d.configured || !!d.armed || state.evaluation?.status==='running';
  el('dota-arm').hidden=!!d.armed;el('dota-disarm').hidden=!d.armed;
  const hero=d.game?.hero?.name==='npc_dota_hero_invoker'?'Invoker':'Sin Invoker';
  el('dota-status').textContent=d.armed?(d.active?'Invocación activa · '+hero+(d.invoke_ready===false?' · Invoke no disponible':''):'Invocación suspendida · '+(d.ready?'Vuelve a Dota':d.reason)):d.reason||'Dota conectado · activa la invocación';
  const status={orb_selected:'Orbe colocado',sent_waiting_gsi:'Invoke enviado; esperando confirmación',observed_in_gsi:'Hechizo preparado en D · confirmado por Dota',already_available:'Ese hechizo ya está preparado en D',unconfirmed:'Sin confirmación GSI; desactivado',cancelled:'Secuencia cancelada',rejected:'Evento rechazado'};
  const orbNames={Q:'Quas',W:'Wex',E:'Exort'};
  const action=d.last_action;
  el('dota-action').textContent=action?(status[action.status]||action.status)+' · '+(action.spell||orbNames[action.token]||'')+(action.reason?' · '+action.reason:''):'';
  el('output-note').textContent=d.armed?'Invocación con sellos activada para tu Invoker. Lanza con D/F como siempre.':'Modo entrenador: las recetas se muestran aquí. Invoke permanece desactivado.';
}

function avcCodec(data) {
  for(let i=0;i<data.length-7;i++) {
    let start=-1;
    if(data[i]===0 && data[i+1]===0 && data[i+2]===1) start=i+3;
    else if(data[i]===0 && data[i+1]===0 && data[i+2]===0 && data[i+3]===1) start=i+4;
    if(start>=0 && (data[start]&31)===7) return 'avc1.'+[data[start+1],data[start+2],data[start+3]].map(x=>x.toString(16).padStart(2,'0')).join('');
  }
  throw new Error('No se recibió la configuración H264.');
}

function stopPreview() { videoAbort?.abort(); }

function startPreview() {
  if(!('VideoDecoder' in window)) {el('video-message').hidden=false;el('video-message').textContent='Abre este panel en Chrome para ver la cámara. El reconocimiento sigue activo.';return;}
  const abort = new AbortController();videoAbort=abort;
  previewTask=(async()=>{
    let decoder, configData, buffer=new Uint8Array(), decoderError, cursor=0, generation=-1, latestPacketPts=0, animation, renderer;
    try {
      el('video-message').hidden=false;el('video-message').textContent='Conectando vista previa…';
      const canvas=el('video'),ctx=canvas.getContext('2d',{alpha:false});
      frameIntervals=[];lastPreviewFrameAt=null;previewMeasureAt=null;previewFrames=0;
      renderer=new PtsPreview((frame,now)=>{
        if(canvas.width!==frame.displayWidth)canvas.width=frame.displayWidth;if(canvas.height!==frame.displayHeight)canvas.height=frame.displayHeight;
        ctx.drawImage(frame,0,0);notePreviewFrame(now);videoPts=frame.timestamp;videoSeenAt=Date.now();drawJoints();el('video-message').hidden=true;
      },()=>state.settings||{});
      const present=now=>{if(abort.signal.aborted)return;renderer.tick(now);animation=requestAnimationFrame(present);};
      animation=requestAnimationFrame(present);
      while(!abort.signal.aborted) {
        const response=await fetch('/video?cursor='+cursor+'&generation='+generation,{signal:abort.signal});
        if(!response.ok) throw new Error('No se pudo abrir la vista previa.');
        const value=new Uint8Array(await response.arrayBuffer());
        const nextGeneration=Number(response.headers.get('X-Video-Generation'));
        if(value.length && nextGeneration!==generation){if(decoder)decoder.close();decoder=null;renderer.reset();latestPacketPts=0;}
        if(value.length){cursor=Number(response.headers.get('X-Video-Cursor'));generation=nextGeneration;}
        buffer=value;
        // Decode every dependency, but do not present an old startup GOP.
        for(let offset=0;offset+12<=value.length;){
          const v=new DataView(value.buffer,value.byteOffset+offset),flags=v.getBigUint64(0),length=v.getUint32(8);
          if(length>8*1024*1024 || offset+12+length>value.length)break;
          if((flags&(1n<<62n))===0n)latestPacketPts=Math.max(latestPacketPts,Number(flags&((1n<<61n)-1n)));
          offset+=12+length;
        }
        while(buffer.length>=12) {
          const view=new DataView(buffer.buffer,buffer.byteOffset,buffer.byteLength),flags=view.getBigUint64(0),length=view.getUint32(8);
          if(length>8*1024*1024) throw new Error('Paquete de vídeo inválido.');
          if(buffer.length<12+length)break;
          const payload=buffer.slice(12,12+length);buffer=buffer.slice(12+length);
          const config=(flags&(1n<<62n))!==0n,key=(flags&(1n<<61n))!==0n,pts=Number(flags&((1n<<61n)-1n));
          if(config) {
            configData=payload;
            if(decoder)decoder.close();
            const options={codec:avcCodec(payload),hardwareAcceleration:'prefer-hardware',optimizeForLatency:true};
            let support=await VideoDecoder.isConfigSupported(options);
            if(!support.supported){options.hardwareAcceleration='no-preference';support=await VideoDecoder.isConfigSupported(options);}
            if(!support.supported)throw new Error('Chrome no ofrece un decoder compatible con '+options.codec+'.');
            el('preview-backend').textContent=options.hardwareAcceleration==='prefer-hardware'?'Preferencia hardware':'Decoder del navegador · reconocimiento en CUDA';
            renderer.reset();const decoderGeneration=generation;
            decoder=new VideoDecoder({output:frame=>{if(abort.signal.aborted||decoderGeneration!==generation){frame.close();return;}renderer.push(frame,performance.now(),latestPacketPts);},error:error=>{decoderError=error;abort.abort();}});
            decoder.configure(options);continue;
          }
          if(!decoder)continue;
          if(decoder.decodeQueueSize>64)throw new Error('La vista previa se retrasó; reconectando…');
          let data=payload;
          if(key && configData) {data=new Uint8Array(configData.length+payload.length);data.set(configData);data.set(payload,configData.length);}
          decoder.decode(new EncodedVideoChunk({type:key?'key':'delta',timestamp:pts,data}));
        }
        await new Promise(resolve=>setTimeout(resolve,15));
      }
      if(decoderError)throw decoderError;
    } catch(error) {
      if(error.name!=='AbortError' || decoderError) {nextPreviewAt=Date.now()+5000;el('video-message').hidden=false;el('video-message').textContent=(decoderError?.message||error.message)+' El reconocimiento sigue activo.';}
    } finally {
      cancelAnimationFrame(animation);renderer?.reset();
      if(decoder && decoder.state!=='closed')decoder.close();previewTask=null;videoAbort=null;
    }
  })();
}

const bones=[[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]];
function drawJoints(){
  const canvas=el('joints'),video=el('video');
  if(canvas.width!==video.width)canvas.width=video.width;
  if(canvas.height!==video.height)canvas.height=video.height;
  canvas.dataset.videoPts=String(videoPts);canvas.dataset.posePts=String(state.poses?.at(-1)?.pts_us);
  const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);
  let pose=(state.poses||[]).filter(p=>videoPts!==null && p.pts_us<=videoPts && videoPts-p.pts_us<=150000 && state.server_monotonic_ms-p.timestamp_ms<=300).at(-1);
  if(!jointsEnabled||state.status!=='running'||Date.now()-videoSeenAt>300||!pose){el('joints-status').textContent=jointsEnabled?'Articulaciones · esperando imagen coincidente':'Articulaciones ocultas';return;}
  el('joints-status').textContent=pose.hands.length+' mano'+(pose.hands.length===1?'':'s')+' · puntos firmes en color, inciertos en gris';
  const sx=canvas.width/pose.dimensions[0],sy=canvas.height/pose.dimensions[1];
  pose.hands.forEach((hand,i)=>{
    const color=i?'#f7b84b':'#57e3e7',p=hand.joints;
    const valid=k=>k.every(Number.isFinite)&&k[0]>=0&&k[0]<=pose.dimensions[0]&&k[1]>=0&&k[1]<=pose.dimensions[1]&&k[2]>.15;
    ctx.lineWidth=3;
    for(const [a,b] of bones){if(!valid(p[a])||!valid(p[b]))continue;ctx.strokeStyle=Math.min(p[a][2],p[b][2])>=.5?color:'#a4a9ad';ctx.globalAlpha=Math.min(p[a][2],p[b][2])>=.5?.9:.35;ctx.beginPath();ctx.moveTo(p[a][0]*sx,p[a][1]*sy);ctx.lineTo(p[b][0]*sx,p[b][1]*sy);ctx.stroke();}
    for(const k of p){if(!valid(k))continue;ctx.globalAlpha=k[2]>=.5?1:.4;ctx.fillStyle=k[2]>=.5?color:'#a4a9ad';ctx.beginPath();ctx.arc(k[0]*sx,k[1]*sy,4,0,2*Math.PI);ctx.fill();}
    ctx.globalAlpha=1;
  });
}
el('joints-toggle').onclick=()=>{jointsEnabled=!jointsEnabled;el('joints-toggle').textContent=jointsEnabled?'Ocultar articulaciones':'Mostrar articulaciones';el('joints-toggle').setAttribute('aria-pressed',String(jointsEnabled));localStorage.setItem('jutsu-joints-visible',String(jointsEnabled));drawJoints();};
setInterval(drawJoints,100);
el('cancel').onclick=()=>control('cancel');
el('reconnect').onclick=()=>control('reconnect',{facing:el('camera').value});
el('camera').onchange=()=>control('reconnect',{facing:el('camera').value});
el('camera-toggle').onclick=()=>control(['running','starting'].includes(state.status)?'stop':'start');
el('record-toggle').onclick=()=>control(state.recording?'record/stop':'record/start',{label:el('record-label').value});
el('preview-toggle').onclick=()=>{
  previewEnabled=!previewEnabled;el('preview-toggle').textContent=previewEnabled?'Ocultar vídeo':'Mostrar vídeo';el('preview-toggle').setAttribute('aria-pressed',String(previewEnabled));
  document.querySelector('.workspace').classList.toggle('preview-hidden',!previewEnabled);
  if(!previewEnabled){stopPreview();el('video-message').hidden=false;el('video-message').textContent='Vista previa oculta. El reconocimiento sigue activo.';}else if(state.status==='running'&&!previewTask)startPreview();
};

async function poll() {
  try {const response=await fetch('/api/state');if(!response.ok)throw new Error('Servicio local no disponible.');render(await response.json());el('service-error').textContent='';}
  catch(error) {el('connection').textContent='Servicio desconectado';el('service-error').textContent=error.message;}
  setTimeout(poll,75);
}
fetch('/api/recipes').then(r=>r.json()).then(data=>{
  recipes=data.spells;
  for(const recipe of recipes) {const row=document.createElement('div');row.className='recipe-row';row.textContent=recipe.name;const strong=document.createElement('strong');strong.textContent=recipe.compact.map(t=>({Q:'Mono',W:'Tigre',E:'Caballo',R:'Serpiente'})[t]).join(' → ');row.append(strong);el('recipes').append(row);}
}).catch(error=>{el('service-error').textContent=error.message;});
poll();
window.addEventListener('pagehide',stopPreview);

el('evaluation-start').onclick=()=>control('evaluation/start',{mode:el('eval-mode').value,rounds:Number(el('eval-rounds').value)});
el('evaluation-exclude').onclick=()=>control('evaluation/exclude');
el('evaluation-abort').onclick=()=>control('evaluation/abort');
el('evaluation-confirm').onclick=()=>control('evaluation/confirm');
el('eval-mode').onchange=()=>{el('eval-rounds').disabled=el('eval-mode').value==='recipes';};
el('dota-arm').onclick=()=>{if(sealSound.enabled)sealSound.unlock().catch(soundError);control('dota/arm');};
el('dota-disarm').onclick=()=>control('dota/disarm');

function renderSettings(data){
  const values=data.settings;if(!values)return;
  const signature=JSON.stringify(values);
  if(!settingsDirty && signature!==settingsSignature){
    for(const input of document.querySelectorAll('[data-setting]')){
      const value=values[input.dataset.setting];
      if(input.type==='checkbox')input.checked=value;else input.value=value/Number(input.dataset.scale||1);
    }
    settingsSignature=signature;
  }
  el('settings-save').disabled=data.evaluation?.status==='running'||!!data.settings_pending;
  el('settings-reset').disabled=data.evaluation?.status==='running'||!!data.settings_pending;
  if(data.settings_pending)el('settings-status').textContent='Guardados · aplicando…';
  else if(!settingsDirty && el('settings-status').textContent==='Guardados · aplicando…')settingsStatus('Guardados en este PC');
}
const settingsStatus=message=>{el('settings-status').textContent=message;el('settings-status').dataset.error='false';};
el('settings-form').addEventListener('input',()=>{settingsDirty=true;settingsStatus('Cambios sin guardar');});
el('settings-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;
  const values={};for(const input of document.querySelectorAll('[data-setting]'))values[input.dataset.setting]=input.type==='checkbox'?input.checked:Number(input.value)*Number(input.dataset.scale||1);
  busy=true;el('settings-save').disabled=true;
  try{
    const response=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json','X-Jutsu-Token':token},body:JSON.stringify(values)});
    const data=await response.json();if(!response.ok)throw new Error(data.error);
    settingsDirty=false;settingsSignature=null;render(data);settingsStatus('Guardados en este PC');
  }catch(error){settingsStatus(error.message);el('settings-status').dataset.error='true';}
  finally{busy=false;el('settings-save').disabled=state.evaluation?.status==='running'||!!state.settings_pending;}
});
el('settings-reset').onclick=async()=>{
  if(busy)return;busy=true;
  try{const response=await fetch('/api/settings/reset',{method:'POST',headers:{'X-Jutsu-Token':token}});const data=await response.json();if(!response.ok)throw new Error(data.error);settingsDirty=false;settingsSignature=null;render(data);settingsStatus('Valores recomendados guardados');}
  catch(error){settingsStatus(error.message);el('settings-status').dataset.error='true';}finally{busy=false;}
};
el('joints-toggle').textContent=jointsEnabled?'Ocultar articulaciones':'Mostrar articulaciones';el('joints-toggle').setAttribute('aria-pressed',String(jointsEnabled));

document.addEventListener('visibilitychange',()=>{if(document.hidden)stopPreview();else if(previewEnabled&&state.status==='running'&&!previewTask)startPreview();});

function soundState(){
  const active=sealSound.active;
  el('sound-toggle').textContent=active?'Silenciar sellos':'Activar sonido';
  el('sound-toggle').setAttribute('aria-pressed',String(!!active));
  el('sound-volume').value=sealSound.volume;el('sound-volume-value').textContent=sealSound.volume+'%';
  el('sound-status').textContent=active?'Cuatro sellos · remate al lanzar el hechizo en Dota.':sealSound.enabled?'Pulsa Activar sonido para escuchar los efectos.':'Sonido silenciado.';
}
function soundError(error){el('sound-status').textContent=error.message+' Pulsa Activar sonido para reintentar.';}
const sealSound=new SealSound(soundState);
soundState();
const sealStream=new EventSource('/api/seals');
sealStream.addEventListener('seals',event=>{
  try{const data=JSON.parse(event.data);sealSound.cursor.initialized=true;sealSound.consume(data.events,data.server_monotonic_ms,data.dota_armed);}catch{/* State polling is the fallback. */}
});
window.addEventListener('pagehide',()=>sealStream.close());
el('sound-toggle').onclick=()=>{if(sealSound.active)sealSound.mute();else sealSound.unlock().then(()=>sealSound.play()).catch(soundError);};
el('sound-volume').oninput=event=>sealSound.setVolume(event.target.value);
