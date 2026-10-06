"""Local GSI observation and bounded, focus-checked invocation through uinput."""
from collections import Counter, deque
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import math
from pathlib import Path
import queue
import re
import secrets
import struct
import subprocess
import threading
import time

KEY_CODES = dict(zip('qwertyuiopasdfghjklzxcvbnm', [16,17,18,19,20,21,22,23,24,25,30,31,32,33,34,35,36,37,38,44,45,46,47,48,49,50]))

KEY_CODES.update(dict(zip('1234567890',range(2,12))))
KEY_CODES.update({f'f{i}':183+i-13 for i in range(13,18)})
VIRTUAL_KEYS={'Q':'f13','W':'f14','E':'f15','R':'f16','select':'f17'}


def parse_vdf_keys(text):
    # dotakeys_personal.lst uses literal backslashes, not JSON escape rules.
    tokens = re.findall(r'"[^"\n]*"|[{}]', text)
    index=0
    def obj():
        nonlocal index
        result={}
        while index < len(tokens) and tokens[index] != '}':
            key=tokens[index].strip('"');index+=1
            if index >= len(tokens):raise ValueError('Configuración de teclas truncada')
            if tokens[index]=='{':
                index+=1;value=obj()
                if index >= len(tokens) or tokens[index]!='}':raise ValueError('Llaves inválidas')
                index+=1
            else:value=tokens[index].strip('"');index+=1
            result[key]=value
        return result
    return obj()


def effective_keys(spec):
    keys=dict(spec['Keys'])
    if spec.get('UseHeroBindings')=='1':
        hero=spec.get('Units',spec.get('Heroes',{})).get('npc_dota_hero_invoker',{})
        for role,binding in hero.items():
            keys[role]=binding
    return keys


def read_keymap(path):
    spec=parse_vdf_keys(Path(path).read_text())['KeyBindings']
    return _keymap_from_spec(spec)


def _keymap_from_spec(spec):
    keys=effective_keys(spec)
    roles={'Q':'AbilityPrimary1','W':'AbilityPrimary2','E':'AbilityPrimary3','R':'AbilityUltimate'}
    output={}
    for token,role in roles.items():
        binding=keys.get(role,{})
        key=binding.get('Key','').lower()
        if key not in KEY_CODES or binding.get('Mode')=='-1' or binding.get('Modifier','None').lower() not in {'none',''}:
            raise ValueError(f'Tecla simple verificable ausente para {role}')
        output[token]=key
    if len(set(output.values()))!=4:raise ValueError('Las cuatro teclas deben ser distintas')
    return output


def read_controls(path):
    spec=parse_vdf_keys(Path(path).read_text())['KeyBindings']
    return _controls_from_spec(spec)


def _controls_from_spec(spec):
    keys=effective_keys(spec)
    result=_keymap_from_spec(spec)
    extra={}
    for role in ['HeroSelect','AbilitySecondary1','AbilitySecondary2']:
        binding=keys.get(role,{})
        key=binding.get('Key','').lower()
        if key not in KEY_CODES or binding.get('Modifier','None').lower() not in {'none',''}:
            raise ValueError(f'Tecla simple verificable ausente para {role}')
        extra[role]=key
    all_keys=list(result.values())+list(extra.values())
    if len(set(all_keys))!=len(all_keys):raise ValueError('Orbes, Invoke, selección y lanzamiento deben tener teclas distintas')
    return {'keys':result,'select_key':extra['HeroSelect'],'cast_keys':[extra['AbilitySecondary1'],extra['AbilitySecondary2']]}


def controls_signature(path, controls=None):
    """Relevant effective bindings, independent of formatting and unrelated keys."""
    spec = parse_vdf_keys(Path(path).read_text())['KeyBindings']
    return _signature_from_spec(spec, controls or _controls_from_spec(spec))


def _signature_from_spec(spec, controls):
    protected = set(controls['keys'].values()) | {controls['select_key']} | set(controls['cast_keys'])
    relevant = {}
    for role, binding in effective_keys(spec).items():
        if not isinstance(binding, dict):
            continue
        key = str(binding.get('Key', '')).lower()
        if role.startswith('Ability') or role == 'HeroSelect' or key in protected:
            relevant[role] = {'key':key, 'modifier':str(binding.get('Modifier', 'None')).lower(),
                              'mode':str(binding.get('Mode', '0'))}
    return {'bindings':relevant, 'per_unit_keybinds':str(spec.get('PerUnitKeybinds', '0')),
            'use_hero_bindings':str(spec.get('UseHeroBindings', '0'))}


def install_gsi(root, game_dir, bindings):
    game_dir=Path(game_dir).resolve();bindings=Path(bindings).resolve()
    if not (game_dir/'game/dota/cfg').is_dir():raise ValueError('Directorio de Dota inválido')
    controls=read_controls(bindings);keys=controls['keys']
    directory=root/'runtime/dota';directory.mkdir(parents=True,exist_ok=True)
    os.chmod(directory,0o700)
    config_path=directory/'config.json'
    old=json.loads(config_path.read_text()) if config_path.exists() else {}
    token=old.get('gsi_token') or secrets.token_hex(24)
    target=game_dir/'game/dota/cfg/gamestate_integration/gamestate_integration_jutsu_invoker.cfg'
    if target.exists() and 'Jutsu Invoker' not in target.read_text():
        raise ValueError('El archivo de destino pertenece a otra integración')
    target.parent.mkdir(parents=True,exist_ok=True)
    text='''"Jutsu Invoker"
{
    "uri" "http://127.0.0.1:32148/"
    "timeout" "1.0"
    "buffer" "0.1"
    "throttle" "0.1"
    "heartbeat" "1.0"
    "auth" { "token" "TOKEN" }
    "data"
    {
        "auth" "1"
        "provider" "1"
        "map" "1"
        "player" "1"
        "hero" "1"
        "abilities" "1"
    }
}
'''.replace('TOKEN',token)
    if target.exists() and target.read_text()!=text:
        backup=directory/('previous-gsi-'+str(time.time_ns())+'.cfg');backup.write_bytes(target.read_bytes());os.chmod(backup,0o600)
    target.write_text(text);os.chmod(target,0o600)
    parts=bindings.parts;account=parts[parts.index('userdata')+1] if 'userdata' in parts else None
    if not account or not account.isdigit():raise ValueError('No se puede verificar tu cuenta de Steam desde la ruta de teclas')
    cfg_dir=game_dir/'game/dota/cfg'
    input_cfg=cfg_dir/'jutsu_invoker_input.cfg'
    # Retire only this project's former autoexec line; personal commands stay.
    autoexec=cfg_dir/'autoexec.cfg'
    if autoexec.exists() and input_cfg.exists() and 'Jutsu Invoker' in input_cfg.read_text():
        previous=autoexec.read_text();lines=previous.splitlines(keepends=True)
        remaining=''.join(line for line in lines if line.strip()!='exec jutsu_invoker_input.cfg')
        if remaining!=previous:
            backup=directory/('previous-autoexec-'+str(time.time_ns())+'.cfg');backup.write_bytes(autoexec.read_bytes())
            autoexec.write_text(remaining)
    config={'transport':'direct','input_keys':{**keys,'select':controls['select_key']},'steamid':str(76561197960265728+int(account)),'game_dir':str(game_dir),'bindings':str(bindings),'keys':keys,'gsi_token':token,
            **controls,'port':32148,'bindings_sha256':hashlib.sha256(bindings.read_bytes()).hexdigest(),
            'controls_signature':controls_signature(bindings, controls)}
    config_path.write_text(json.dumps(config,indent=2)+'\n');os.chmod(config_path,0o600)
    return {'status':'installed','gsi_config':str(target),'keys':keys,'requires_launch_option':'-gamestateintegration'}


class Keyboard:
    def __init__(self,keys):
        self.fd=os.open('/dev/uinput',os.O_WRONLY|os.O_NONBLOCK)
        self.down=set()
        try:
            fcntl.ioctl(self.fd,0x40045564,1) # UI_SET_EVBIT / EV_KEY
            fcntl.ioctl(self.fd,0x40045564,0) # EV_SYN
            for key in set(keys):fcntl.ioctl(self.fd,0x40045565,KEY_CODES[key])
            setup=struct.pack('HHHH80sI',3,1,1,1,b'Jutsu Invoker',0)
            fcntl.ioctl(self.fd,0x405c5503,setup) # UI_DEV_SETUP
            fcntl.ioctl(self.fd,0x5501) # UI_DEV_CREATE
        except BaseException:
            os.close(self.fd);raise
        time.sleep(.25)

    def event(self,key,value):
        code=KEY_CODES[key]
        data=struct.pack('llHHi',0,0,1,code,value)+struct.pack('llHHi',0,0,0,0,0)
        if os.write(self.fd,data)!=len(data):raise RuntimeError('Escritura uinput incompleta')
        (self.down.add if value else self.down.discard)(key)

    def release(self):
        for key in list(self.down):self.event(key,0)

    def close(self):
        try:self.release()
        finally:
            try:fcntl.ioctl(self.fd,0x5502)
            finally:os.close(self.fd)


class DotaIntegration:
    """Incremental orbs and one-shot Invoke; eligibility never queues old gestures."""
    def __init__(self,root,keyboard_factory=Keyboard,focus_probe=None,enabled=True,
                 input_guard_factory=None,clock=None,sleeper=None,start_worker=True,start_receiver=True):
        self.root=root;self.lock=threading.RLock();self.keyboard_factory=keyboard_factory
        self.focus_probe=focus_probe or self.focused
        if input_guard_factory is None:
            from .input_guard import InputGuard
            input_guard_factory=InputGuard
        self.input_guard_factory=input_guard_factory;self.input_guard=None
        self.clock=clock or (lambda:time.monotonic()*1000);self.sleep=sleeper or time.sleep
        self.config=None;self.receiver=None;self.keyboard=None
        self.stop_event=threading.Event();self.wake_event=threading.Event();self.pending=queue.Queue(maxsize=1)
        self.seen=deque(maxlen=128);self.armed=False;self.context_generation=0;self.context_active=False;self.context_since_ms=0
        self.updated_ms=None;self.version=0;self.game={};self.last_action=None;self.sent_any=False
        self.problem=None;self.dispatching=False;self.camera_live=False;self.session=None
        self.validated_controls=None
        self.camera_timestamp_ms=None;self.camera_max_age_ms=100;self.camera_context_timeout_ms=1600
        # Fresh input must authorize the start. A bounded continuation tolerates
        # camera jitter while completing that same command; it cannot start one.
        self.camera_send_grace_ms=150
        self.actions=deque(maxlen=64);self.progress=None
        self.prepared_events=deque(maxlen=32);self.on_prepared=lambda event:None
        self.cast_events=deque(maxlen=32);self.on_cast=lambda event:None;self.cast_needs_baseline=True
        self.spells={r['name']:(''.join(sorted(r['orbs'])),'invoker_'+r['name'].lower().replace(' ','_'))
                     for r in (json.loads((root/'diseno/mapa-recetas.json').read_text())['spells'] if enabled else [])}
        path=root/'runtime/dota/config.json'
        if enabled and path.exists():
            self.config=json.loads(path.read_text())
            if start_receiver:
                self.receiver=GsiServer(self,self.config['port'])
                threading.Thread(target=self.receiver.serve_forever,name='jutsu-gsi',daemon=True).start()
        self.worker=None
        if start_worker:
            self.worker=threading.Thread(target=self._worker,name='jutsu-input',daemon=True);self.worker.start()

    def focused(self):
        if not self.config:return False
        try:
            window=json.loads(subprocess.check_output(['hyprctl','-j','activewindow'],timeout=.15))
            binary=Path(f'/proc/{int(window["pid"])}/exe').resolve(strict=True)
            return window.get('xwayland') is True and binary.name=='dota2' and binary.is_relative_to(Path(self.config['game_dir']).resolve())
        except (OSError,ValueError,KeyError,subprocess.SubprocessError):return False

    def receive(self,payload,now_ms=None):
        now=self.clock() if now_ms is None else now_ms
        if not isinstance(payload,dict):raise ValueError('GSI inválido')
        provider=payload.get('provider',{})
        if not isinstance(provider,dict) or provider.get('appid')!=570:raise ValueError('El proveedor no es Dota 2')
        timestamp=provider.get('timestamp')
        if type(timestamp) not in (int,float) or not math.isfinite(timestamp) or abs(time.time()-timestamp)>3:
            raise ValueError('Timestamp GSI ausente o atrasado')
        hero=payload.get('hero',{});player=payload.get('player',{});game_map=payload.get('map',{})
        abilities=payload.get('abilities',{})
        if not all(isinstance(value,dict) for value in [hero,player,game_map,abilities]):raise ValueError('GSI inválido')
        filtered={key:{k:value[k] for k in ['name','level','can_cast','cooldown','charges','max_charges'] if k in value}
                  for key,value in abilities.items() if isinstance(value,dict) and re.fullmatch(r'ability[0-9]+',key)}
        own_player=bool(self.config.get('steamid')) and str(self.config['steamid'])==str(player.get('steamid'))
        with self.lock:
            previous=self.game;previous_ms=self.updated_ms
            session=(game_map.get('matchid'),hero.get('id'),hero.get('name'),own_player,player.get('activity'))
            session_changed=session!=self.session
            if session_changed:
                self.cancel_pending('Cambió la sesión o el héroe');self.context_generation+=1;self.session=session
                if self.last_action and self.last_action['status']=='sent_waiting_gsi':
                    self.last_action.update(status='cancelled',reason='Cambió la sesión o el héroe')
            self.game={'hero':{k:hero[k] for k in ['name','id','alive','silenced','stunned','hexed','selected_unit'] if k in hero},
                       'activity':player.get('activity'),'own_player':own_player,'identity_available':bool(player.get('steamid')),'paused':game_map.get('paused'),
                       'game_state':game_map.get('game_state'),'abilities':filtered}
            self.updated_ms=now;self.version+=1
            self._detect_cast_locked(previous,previous_ms,session_changed,now)
            self._confirm_locked()
            # Sanitized local diagnostic: no auth, account identifier or player names.
            directory=self.root/'runtime/dota';directory.mkdir(parents=True,exist_ok=True)
            (directory/'gsi-last.json').write_text(json.dumps({'received_ms':now,'version':self.version,**self.game},ensure_ascii=False,indent=2)+'\n')

    @staticmethod
    def _cast_scope(game):
        return (game.get('own_player') is True and game.get('activity')=='playing'
                and game.get('hero',{}).get('name')=='npc_dota_hero_invoker'
                and game.get('hero',{}).get('alive') is True and game.get('paused') is False
                and game.get('game_state') in {'DOTA_GAMERULES_STATE_PRE_GAME','DOTA_GAMERULES_STATE_GAME_IN_PROGRESS'})

    def _detect_cast_locked(self,previous,previous_ms,session_changed,now):
        eligible=self.armed and self._cast_scope(self.game)
        baseline=(not self.cast_needs_baseline and not session_changed and self._cast_scope(previous)
                  and previous_ms is not None and 0<=now-previous_ms<=1500)
        self.cast_needs_baseline=not eligible
        if not eligible or not baseline:return
        names={ability:spell for spell,(_,ability) in self.spells.items()}
        # Compare by spell identity: Invoke swaps D/F, without casting either.
        before={a.get('name'):a for slot in ['ability3','ability4']
                if (a:=previous.get('abilities',{}).get(slot,{})).get('name') in names}
        after=[(slot,a) for slot in ['ability3','ability4']
               if (a:=self.game.get('abilities',{}).get(slot,{})).get('name') in names]
        if len({a['name'] for _,a in after})!=len(after):return
        for slot,current in after:
            old=before.get(current['name'])
            if not old or type(current.get('level')) is not int or current['level']<1 or old.get('level')!=current['level']:continue
            prior,cd=old.get('cooldown'),current.get('cooldown')
            cooldown=(type(prior) in (int,float) and type(cd) in (int,float)
                      and math.isfinite(prior) and math.isfinite(cd) and prior==0 and cd>0)
            charges=(type(old.get('charges')) is int and type(current.get('charges')) is int
                     and type(current.get('max_charges')) is int and current['max_charges']>0
                     and old.get('max_charges')==current['max_charges']
                     and 0<=current['charges']<old['charges']<=current['max_charges'])
            if not cooldown and not charges:continue
            event={'type':'cast','spell':names[current['name']],'ability':current['name'],'slot':slot,
                   'evidence':'cooldown_started' if cooldown else 'charge_spent',
                   'timestamp_ms':now,'received_ms':now}
            self.cast_events.append(event);self.on_cast(event)

    def ready(self,now=None,orbs=None,invoke=True,context=False,continuing=False):
        now=self.clock() if now is None else now
        if not self.config:return False,'Enlace de Dota sin habilitar; inicia con --dota'
        if self.updated_ms is None or now-self.updated_ms>1500 or now<self.updated_ms:return False,'Esperando estado reciente de Dota; requiere -gamestateintegration'
        h=self.game.get('hero',{})
        if not self.game.get('own_player'):return False,'El estado no corresponde a tu propio héroe'
        if self.game.get('activity')!='playing':return False,'Menú, chat o espectador: invocación suspendida'
        if h.get('name')!='npc_dota_hero_invoker':return False,'Solo funciona al jugar Invoker'
        if h.get('alive') is not True:return False,'Invoker está muerto'
        if self.game.get('game_state') not in {'DOTA_GAMERULES_STATE_PRE_GAME','DOTA_GAMERULES_STATE_GAME_IN_PROGRESS'}:return False,'Esperando una sesión activa'
        if self.game.get('paused') is not False:return False,'Partida pausada o estado desconocido'
        if any(h.get(k) is not False for k in ['silenced','stunned','hexed']):return False,'Invoker no puede usar habilidades ahora'
        abilities=self.game.get('abilities',{})
        needed=set('QWE' if orbs is None else orbs) | ({'R'} if invoke else set())
        for slot,name in [(0,'invoker_quas'),(1,'invoker_wex'),(2,'invoker_exort'),(5,'invoker_invoke')]:
            ability=abilities.get(f'ability{slot}',{})
            if ability.get('name')!=name:return False,'El modo cambió las ranuras de Invoker; envío suspendido'
            token={0:'Q',1:'W',2:'E',5:'R'}[slot]
            if token in needed and (type(ability.get('level')) is not int or ability['level']<1 or ability.get('can_cast') is not True or type(ability.get('cooldown')) not in (int,float) or not math.isfinite(ability['cooldown']) or ability['cooldown']!=0):
                return False,'Orbes o Invoke no disponibles'
        camera_ok=self.camera_live
        if self.camera_timestamp_ms is not None:
            limit=self.camera_context_timeout_ms if context else self.camera_max_age_ms+(self.camera_send_grace_ms if continuing else 0)
            camera_ok=(context or continuing or self.camera_live) and 0<=now-self.camera_timestamp_ms<=limit
        if not camera_ok:
            return False,'Cámara detenida o imagen atrasada'
        if self.input_guard and self.input_guard.blocked:
            return False,'Chat o consola: cierra con Escape en Dota antes de hacer sellos'
        return True,'Listo para invocar' if invoke else 'Listo para preparar orbes'

    def verify_input_config(self):
        if self.config.get('transport')=='direct':return
        path=Path(self.config['input_config'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=self.config.get('input_sha256'):
            raise ValueError('El enlace de teclas virtuales cambió; vuelve a configurarlo')

    def verify_controls(self):
        self.verify_input_config()
        # Read and hash before EVERY key. Reparse only changed bytes or changed
        # expectations, using one immutable snapshot for all effective controls.
        contents=Path(self.config['bindings']).read_bytes()
        digest=hashlib.sha256(contents).hexdigest()
        expectation=json.dumps({k:self.config.get(k) for k in
                                ['keys','select_key','cast_keys','controls_signature','bindings_sha256']},sort_keys=True)
        if self.validated_controls==(digest,expectation):return
        spec=parse_vdf_keys(contents.decode())['KeyBindings']
        controls=_controls_from_spec(spec)
        if controls!={k:self.config[k] for k in ['keys','select_key','cast_keys']}:
            raise RuntimeError('Las teclas de Dota cambiaron')
        signature=self.config.get('controls_signature')
        if signature is not None:
            if _signature_from_spec(spec,controls)!=signature:
                raise RuntimeError('Las teclas de Dota cambiaron')
        else:
            # Legacy installations retain the strict check until explicitly installed again.
            expected=self.config.get('bindings_sha256')
            if expected and digest!=expected:
                raise RuntimeError('Las teclas de Dota cambiaron')
        self.validated_controls=(digest,expectation)

    def arm(self):
        with self.lock:
            if not self.config:raise ValueError('Inicia el servicio con --dota')
            self.verify_controls()
            controls=read_controls(self.config['bindings'])
            if any(controls[k]!=self.config.get(k) for k in controls):raise ValueError('Las teclas cambiaron; actualiza la configuración de Dota')
            if self.keyboard is None:self.keyboard=self.keyboard_factory(self.config['input_keys'].values())
            if self.input_guard is None:
                try:self.input_guard=self.input_guard_factory([*self.config['keys'].values(),self.config['select_key'],*self.config['cast_keys']])
                except Exception:
                    self.keyboard.close();self.keyboard=None;raise
            self.input_guard.focus_probe=self.focus_probe
            self.input_guard.blocked  # Drain earlier input before the explicit activation.
            self.input_guard.text_blocked=False
            if self.config.get('transport')=='direct' and not self.input_guard.tracking_available:
                raise ValueError('El envío directo requiere el filtro XI2 de entrada manual')
            self.cancel_pending('Integración activada');self.armed=True;self.cast_needs_baseline=True;self.problem=None;self.context_generation+=1

    def cancel_pending(self,reason='Receta cancelada'):
        with self.lock:
            if self.config is None:return
            self.context_generation+=1;self.context_since_ms=self.clock();self.progress=None
            while True:
                try:self.pending.get_nowait()
                except queue.Empty:break

    def disarm(self,reason='Desactivado'):
        with self.lock:
            self.armed=False;self.cast_needs_baseline=True;self.problem=reason;self.cancel_pending(reason)

    def _action(self,value):
        with self.lock:
            self.last_action=value;self.actions.append(value)
            if value['status']=='already_available':self._notify_prepared(value)

    def _notify_prepared(self,action):
        stamp=self.clock()
        event={'type':'prepared','spell':action['spell'],'timestamp_ms':stamp,'received_ms':stamp}
        self.prepared_events.append(event)
        self.on_prepared(event)

    def submit(self,event):
        with self.lock:
            stamp=event.get('timestamp_ms');now=self.clock();kind=event.get('type')
            spell=event.get('spell');orbs=event.get('orbs');token=event.get('token');prefix=event.get('pending')
            if type(stamp) not in (int,float) or not math.isfinite(stamp):return
            if kind=='accepted':
                if token not in {'Q','W','E'} or not isinstance(prefix,list) or not 1<=len(prefix)<=3 or any(o not in {'Q','W','E'} for o in prefix) or len(set(prefix))!=len(prefix) or prefix[-1]!=token:return
                required=token
            elif kind=='recipe':
                if not isinstance(orbs,str) or spell not in self.spells or ''.join(sorted(orbs))!=self.spells[spell][0]:return
                sequence=event.get('sequence')
                if sequence is not None:
                    if not isinstance(sequence,list) or len(sequence)<2 or sequence[-1]!='R':return
                    selectors=sequence[:-1]
                    if any(o not in {'Q','W','E'} for o in selectors) or len(set(selectors))!=len(selectors) or len(selectors)>3:return
                    formula=selectors[0]*3 if len(selectors)==1 else selectors[0]*2+selectors[1] if len(selectors)==2 else 'QWE'
                    if Counter(formula)!=Counter(orbs):return
                required=orbs
            else:return
            if now-stamp>500 or stamp>now or stamp<self.context_since_ms or event.get('dota_context_generation',self.context_generation)!=self.context_generation:return
            key=(stamp,kind,spell if kind=='recipe' else tuple(prefix))
            if key in self.seen:return
            if kind=='accepted' and self.progress and self.progress['selectors']==prefix:return
            self.seen.append(key)
            if not self.armed:return
            if self.dispatching or not self.pending.empty() or self.last_action and self.last_action['status']=='sent_waiting_gsi':
                self.progress=None
                self.actions.append({'status':'rejected','reason':'Invocación ocupada','spell':spell,'token':token});return
            ok,reason=self.ready(now,required,kind=='recipe')
            if not ok:
                self.progress=None
                self._action({'status':'rejected','reason':reason,'spell':spell,'token':token});return
            focused=self.focus_probe()
            if not focused or not self.input_guard.clear():
                self.progress=None
                reason='Dota sin foco' if not focused else 'Teclas de habilidad o modificadores presionados'
                self._action({'status':'rejected','reason':reason,'spell':spell,'token':token});return
            # Authorization begins here, while the image is fresh. The focus and
            # Xwayland checks themselves can cross the camera's 100 ms boundary.
            self.pending.put_nowait({**event,'context_generation':self.context_generation,'camera_authorized_ms':now})
            self.wake_event.set()

    def _require_allowed(self,deadline,epoch,orbs,invoke,manual_epoch,continuing=False):
        now=self.clock()
        if now>deadline:raise RuntimeError('El gesto caducó antes de completar el envío')
        if not self.armed:raise RuntimeError('Invocación desactivada durante el envío')
        if epoch!=self.context_generation:raise RuntimeError('Cambió el contexto durante el envío')
        ok,reason=self.ready(now,orbs,invoke,continuing=continuing)
        if not ok:raise RuntimeError(reason)
        if not self.focus_probe():raise RuntimeError('Dota perdió el foco durante el envío')
        if not self.input_guard.clear():raise RuntimeError('Teclas de habilidad o modificadores presionados')
        if self.input_guard.epoch!=manual_epoch:raise RuntimeError('Entrada manual durante el envío')

    def _confirm_locked(self):
        action=self.last_action
        if action and action['status']=='sent_waiting_gsi' and self.version>action['gsi_version']:
            if self.game.get('own_player') and self.game.get('hero',{}).get('name')=='npc_dota_hero_invoker' and self.game.get('abilities',{}).get('ability3',{}).get('name')==action['ability']:
                action['status']='observed_in_gsi';action['observed_ms']=self.clock()
                self._notify_prepared(action)

    def _send(self,event):
        deadline=event['timestamp_ms']+500;epoch=event['context_generation']
        selecting=event['type']=='accepted';orbs=event['token'] if selecting else event['orbs']
        spell=event.get('spell');ability=None if selecting else self.spells[spell][1];sent=[]
        with self.lock:
            self.dispatching=True;version=self.version;manual_epoch=self.input_guard.epoch
            progress=self.progress
        try:
            self._require_allowed(deadline,epoch,orbs,not selecting,manual_epoch,
                                  continuing=event.get('camera_authorized_ms') is not None)
            self.verify_controls()
            if not selecting and self.game.get('abilities',{}).get('ability3',{}).get('name')==ability:
                self.progress=None
                self._action({'status':'already_available','spell':spell,'ability':ability,'keys':[]});return
            tracking=self.input_guard.tracking_available
            valid=bool(progress and progress['valid'] and progress['manual_epoch']==manual_epoch)
            if selecting:
                prefix=event['pending']
                valid=tracking and (len(prefix)==1 or valid and progress['selectors']==prefix[:-1])
                remaining=orbs
            else:
                selectors=event.get('sequence',[])[:-1]
                valid=valid and tracking and progress['selectors']==selectors and not (Counter(progress['orbs'])-Counter(orbs))
                remaining=''.join((Counter(orbs)-Counter(progress['orbs'])).elements()) if valid else orbs
            # Three fresh orb commands overwrite the old ring. A validated prefix
            # contributes its already sent orbs; only the missing counts precede R.
            sequence=[self.config['input_keys']['select']]+[self.config['input_keys'][o] for o in remaining+('' if selecting else 'R')]
            for key in sequence:
                self.verify_controls()
                self._require_allowed(deadline,epoch,orbs,not selecting,manual_epoch,continuing=True)
                self.input_guard.expect(key)
                if self.input_guard.blocked or self.input_guard.epoch!=manual_epoch:
                    raise RuntimeError('Entró una pulsación manual antes del envío')
                self.keyboard.event(key,1);sent.append(key);self.sent_any=True
                self.sleep(.025);self.keyboard.event(key,0);self.sleep(.025)
            with self.lock:
                if epoch!=self.context_generation or self.input_guard.epoch!=manual_epoch:
                    raise RuntimeError('Cambió el contexto durante el envío')
                if selecting:
                    self.progress={'selectors':prefix.copy(),'orbs':''.join(prefix),'manual_epoch':manual_epoch,'valid':valid}
                    self._action({'status':'orb_selected','token':orbs,'keys':sent,'sent_ms':self.clock(),'prefix_valid':valid})
                else:
                    self.progress=None
                    self._action({'status':'sent_waiting_gsi','spell':spell,'ability':ability,'keys':sent,
                                  'completion_orbs':remaining,'repaired':not valid,'gsi_version':version,
                                  'context_generation':epoch,'sent_ms':self.clock()})
                    self._confirm_locked()
        except Exception as error:
            self._action({'status':'cancelled','reason':str(error),'spell':spell,'token':event.get('token'),'keys':sent,
                          'camera_age_ms':self.clock()-self.camera_timestamp_ms if self.camera_timestamp_ms is not None else None,
                          'manual_epoch_changed':self.input_guard.epoch!=manual_epoch})
            if str(error)=='Las teclas de Dota cambiaron':self.disarm(str(error))
            elif epoch!=self.context_generation or not self.ready(orbs='',invoke=False,context=True)[0] or not self.focus_probe():
                self.cancel_pending(str(error))
            else:
                # A stale frame or manual key aborts this send. Preserve the gesture
                # recipe; its next confirmation must rebuild all three orb counts.
                with self.lock:
                    self.progress=None
                    while True:
                        try:self.pending.get_nowait()
                        except queue.Empty:break
        finally:
            if self.keyboard:self.keyboard.release()
            with self.lock:self.dispatching=False

    def tick(self):
        with self.lock:
            now=self.clock();active=bool(self.armed and self.ready(now,'',False,context=True)[0] and self.focus_probe())
            if active!=self.context_active:
                self.context_active=active;self.cancel_pending('Cambió la disponibilidad de Dota')
            if self.last_action and self.last_action['status']=='sent_waiting_gsi' and now-self.last_action['sent_ms']>1500:
                # Losing one acknowledgement must not permanently disable input.
                # Discard its prefix and queued gestures; only fresh, newly
                # authorized poses may start again. Never retry the old Invoke.
                self.last_action.update(status='unconfirmed',reason='Dota no confirmó esta receta; empieza una nueva')
                self.cancel_pending('Invoke sin confirmación GSI; no se reintenta')
                return
            if not active:return
            try:event=self.pending.get_nowait()
            except queue.Empty:return
        self._send(event)

    def _worker(self):
        while not self.stop_event.is_set():
            self.wake_event.wait(.05);self.wake_event.clear()
            if self.stop_event.is_set():break
            try:self.tick()
            except Exception as error:self.disarm(str(error))

    def snapshot(self):
        with self.lock:
            now=self.clock();ready,reason=self.ready(now,'',False)
            return {'configured':self.config is not None,'gsi_received':self.updated_ms is not None,
                    'gsi_age_ms':now-self.updated_ms if self.updated_ms is not None else None,
                    'ready':ready,'invoke_ready':self.ready(now,'',True)[0],
                    'reason':self.problem or reason,'armed':self.armed,'active':self.context_active and ready,
                    'keys':self.config['keys'] if self.config else None,
                    'cast_keys':self.config.get('cast_keys') if self.config else None,
                    'select_key':self.config.get('select_key') if self.config else None,
                    'input_keys':self.config.get('input_keys') if self.config else None,
                    'game':self.game,'last_action':self.last_action,'game_input_sent':self.sent_any,
                    'context_generation':self.context_generation,'actions':list(self.actions),'prepared_events':list(self.prepared_events),'cast_events':list(self.cast_events),
                    'progress':self.progress,'manual_tracking':bool(self.input_guard and self.input_guard.tracking_available)}

    def close(self):
        self.disarm('Servicio cerrado');self.stop_event.set();self.wake_event.set()
        if self.worker:self.worker.join(timeout=3)
        if self.receiver:self.receiver.shutdown();self.receiver.server_close()
        if self.keyboard:self.keyboard.close();self.keyboard=None
        if self.input_guard:self.input_guard.close();self.input_guard=None


class GsiServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,integration,port):
        self.integration=integration
        super().__init__(('127.0.0.1',port),GsiHandler)


class GsiHandler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        self.connection.settimeout(3)
        status=200
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=65536:raise ValueError('Tamaño GSI inválido')
            payload=json.loads(self.rfile.read(length))
            if not isinstance(payload,dict) or not isinstance(payload.get('auth',{}),dict):raise ValueError('GSI inválido')
            token=payload.get('auth',{}).get('token','')
            if not isinstance(token,str) or not secrets.compare_digest(token,self.server.integration.config['gsi_token']):
                status=403
            else:self.server.integration.receive(payload)
        except (ValueError,KeyError,TypeError,OSError):status=400
        self.send_response(status);self.send_header('Content-Length','0');self.end_headers()
