from copy import deepcopy
import json
import hashlib
from pathlib import Path
import tempfile
import time
import unittest
from jutsu_invoker.dota import DotaIntegration, read_controls

ROOT=Path(__file__).resolve().parents[1]

class FakeKeyboard:
    def __init__(self,keys):self.keys=set(keys);self.events=[];self.down=set();self.hook=None
    def event(self,key,value):
        self.events.append((key,value))
        (self.down.add if value else self.down.discard)(key)
        if self.hook:self.hook(key,value)
    def release(self):
        for key in list(self.down):self.event(key,0)
    def close(self):self.release()

class FakeGuard:
    def __init__(self,keys):self.free=True;self.epoch=0;self.tracking_available=True;self.text_blocked=False
    def clear(self):return self.free and not self.text_blocked
    def expect(self,key):pass
    @property
    def blocked(self):return self.text_blocked
    def close(self):pass

class DotaTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'runtime/dota').mkdir(parents=True);(self.root/'diseno').mkdir()
        (self.root/'diseno/mapa-recetas.json').write_bytes((ROOT/'diseno/mapa-recetas.json').read_bytes())
        self.bindings=self.root/'keys.lst'
        roles=dict(AbilityPrimary1='q',AbilityPrimary2='w',AbilityPrimary3='e',AbilityUltimate='r',AbilitySecondary1='d',AbilitySecondary2='f',HeroSelect='2')
        self.bindings.write_text('"KeyBindings" { "Keys" {'+' '.join(f'"{r}" {{ "Key" "{k}" }}' for r,k in roles.items())+'} }')
        input_config=self.root/'input.cfg';input_config.write_text('test-only-placeholder')
        self.config={'input_config':str(input_config),'input_sha256':hashlib.sha256(input_config.read_bytes()).hexdigest(),'input_keys':{'Q':'f13','W':'f14','E':'f15','R':'f16','select':'f17'},'keys':{'Q':'q','W':'w','E':'e','R':'r'},'select_key':'2','cast_keys':['d','f'],'bindings':str(self.bindings),'steamid':'123','port':0,'game_dir':str(self.root)}
        (self.root/'runtime/dota/config.json').write_text(json.dumps(self.config))
        self.now=1000.;self.focus=True
        self.app=DotaIntegration(self.root,FakeKeyboard,lambda:self.focus,input_guard_factory=FakeGuard,clock=lambda:self.now,sleeper=self.advance,start_worker=False,start_receiver=False)
        self.app.camera_live=True
        self.payload={'provider':{'appid':570,'timestamp':time.time()},'player':{'steamid':'123','activity':'playing'},'map':{'paused':False,'matchid':'1','game_state':'DOTA_GAMERULES_STATE_GAME_IN_PROGRESS'},'hero':{'name':'npc_dota_hero_invoker','id':74,'alive':True,'silenced':False,'stunned':False,'hexed':False},'abilities':{f'ability{i}':{'name':n,'level':1,'can_cast':True,'cooldown':0} for i,n in enumerate(['invoker_quas','invoker_wex','invoker_exort','invoker_empty1','invoker_empty2','invoker_invoke'])}}
        self.app.receive(self.payload);self.app.arm();self.app.tick()
    def tearDown(self):self.app.close();self.temp.cleanup()
    def advance(self,seconds):self.now+=seconds*1000
    def event(self,spell='Cold Snap',orbs='QQQ'):return {'type':'recipe','spell':spell,'orbs':orbs,'timestamp_ms':self.now}
    def confirm_on_invoke(self,spell):
        def hook(key,value):
            if (key,value)==('f16',1):
                p=deepcopy(self.payload);p['abilities']['ability3']['name']=self.app.spells[spell][1];self.app.receive(p)
        self.app.keyboard.hook=hook
    def test_all_ten_recipes_only_select_orbs_and_invoke_never_cast(self):
        for spell,(orbs,_) in self.app.spells.items():
            with self.subTest(spell=spell):
                self.app.last_action=None;self.confirm_on_invoke(spell);before=len(self.app.keyboard.events)
                self.app.submit(self.event(spell,orbs));self.app.tick()
                events=self.app.keyboard.events[before:]
                self.assertEqual([k for k,v in events if v],['f17']+[self.config['input_keys'][o] for o in orbs+'R'])
                self.assertFalse(self.app.keyboard.down);self.assertEqual(self.app.last_action['status'],'observed_in_gsi')
                self.assertTrue(self.app.armed);self.assertNotIn('d',self.app.keyboard.keys);self.assertNotIn('f',self.app.keyboard.keys)
    def select(self,token,prefix):
        self.app.submit({'type':'accepted','token':token,'pending':prefix.copy(),'timestamp_ms':self.now})
        self.app.tick()

    def test_incremental_all_ten_and_all_distinct_orders(self):
        from itertools import permutations
        recipes=json.loads((ROOT/'diseno/mapa-recetas.json').read_text())['spells']
        cases=[(r['name'],r['orbs'],r['compact'][:-1]) for r in recipes]
        cases += [('Deafening Blast','QWE',list(seq)) for seq in permutations('QWE')]
        for spell,orbs,selectors in cases:
            with self.subTest(spell=spell,selectors=selectors):
                self.app.receive(self.payload);self.app.last_action=None;self.app.cancel_pending();self.app.tick()
                self.app.game['abilities']['ability3']['name']='invoker_empty1'
                start=len(self.app.keyboard.events);prefix=[]
                for token in selectors:
                    prefix.append(token);before=len(self.app.keyboard.events)
                    self.select(token,prefix)
                    self.assertEqual([k for k,v in self.app.keyboard.events[before:] if v],['f17',self.config['input_keys'][token]])
                    self.assertEqual(self.app.last_action['status'],'orb_selected')
                    self.assertNotIn(('f16',1),self.app.keyboard.events[start:])
                    self.app.receive(self.payload)
                self.confirm_on_invoke(spell);before=len(self.app.keyboard.events)
                self.app.submit(self.event(spell,orbs)|{'sequence':selectors+['R']});self.app.tick()
                completion=[k for k,v in self.app.keyboard.events[before:] if v]
                from collections import Counter
                missing=''.join((Counter(orbs)-Counter(selectors)).elements())
                self.assertEqual(completion,['f17']+[self.config['input_keys'][o] for o in missing]+['f16'])
                all_orbs=[k for k,v in self.app.keyboard.events[start:] if v and k in {'f13','f14','f15'}]
                self.assertEqual(Counter(all_orbs),Counter(self.config['input_keys'][o] for o in orbs))
                self.assertFalse(self.app.last_action['repaired']);self.assertEqual(self.app.last_action['status'],'observed_in_gsi')

    def test_manual_input_between_poses_repairs_three_orbs(self):
        self.select('Q',['Q']);self.app.input_guard.epoch+=1
        self.select('W',['Q','W']);self.assertFalse(self.app.progress['valid'])
        self.confirm_on_invoke('Ghost Walk');before=len(self.app.keyboard.events)
        self.app.submit(self.event('Ghost Walk','QQW')|{'sequence':['Q','W','R']});self.app.tick()
        self.assertEqual([k for k,v in self.app.keyboard.events[before:] if v],['f17','f13','f13','f14','f16'])
        self.assertTrue(self.app.last_action['repaired'])

    def test_manual_input_during_completion_aborts_before_invoke(self):
        self.select('Q',['Q']);self.select('W',['Q','W'])
        def hook(k,v):
            if k=='f13' and v:self.app.input_guard.epoch+=1
        self.app.keyboard.hook=hook
        self.app.submit(self.event('Ghost Walk','QQW')|{'sequence':['Q','W','R']});self.app.tick()
        self.assertNotIn(('f16',1),self.app.keyboard.events);self.assertFalse(self.app.keyboard.down)
        self.assertEqual(self.app.last_action['status'],'cancelled')

    def test_invoke_cooldown_allows_orbs_but_never_queues_invoke(self):
        p=deepcopy(self.payload);p['abilities']['ability5'].update(can_cast=False,cooldown=2)
        self.app.receive(p);self.app.tick();self.assertTrue(self.app.context_active)
        self.select('Q',['Q']);self.assertEqual(self.app.last_action['status'],'orb_selected')
        count=len(self.app.keyboard.events);self.app.submit(self.event()|{'sequence':['Q','R']});self.app.tick()
        self.assertEqual(len(self.app.keyboard.events),count);self.assertNotIn(('f16',1),self.app.keyboard.events)
        self.app.receive(self.payload);self.app.tick();self.assertEqual(len(self.app.keyboard.events),count)

    def test_unused_unlearned_orb_does_not_block_sun_strike(self):
        p=deepcopy(self.payload);p['abilities']['ability0'].update(level=0,can_cast=False);p['abilities']['ability1'].update(level=0,can_cast=False)
        self.app.receive(p);self.app.tick();self.select('E',['E'])
        self.confirm_on_invoke('Sun Strike');self.app.submit(self.event('Sun Strike','EEE')|{'sequence':['E','R']});self.app.tick()
        self.assertEqual(self.app.last_action['status'],'observed_in_gsi')

    def test_cancelled_or_missing_selector_prefix_is_repaired(self):
        self.select('Q',['Q']);self.app.cancel_pending('timeout')
        self.select('W',['Q','W']);self.assertFalse(self.app.progress['valid'])
        self.confirm_on_invoke('Ghost Walk');self.app.submit(self.event('Ghost Walk','QQW')|{'sequence':['Q','W','R']});self.app.tick()
        self.assertEqual(self.app.last_action['completion_orbs'],'QQW')
        self.assertTrue(self.app.last_action['repaired'])

    def test_missing_manual_tracker_uses_safe_full_completion(self):
        self.app.input_guard.tracking_available=False
        self.select('Q',['Q']);self.confirm_on_invoke('Cold Snap')
        self.app.submit(self.event()|{'sequence':['Q','R']});self.app.tick()
        self.assertEqual(self.app.last_action['completion_orbs'],'QQQ');self.assertTrue(self.app.last_action['repaired'])

    def test_duplicate_selector_event_and_invalid_prefix_never_send_again(self):
        event={'type':'accepted','token':'Q','pending':['Q'],'timestamp_ms':self.now}
        self.app.submit(event);self.app.tick();count=len(self.app.keyboard.events)
        self.app.submit(event);self.app.tick();self.assertEqual(len(self.app.keyboard.events),count)
        for change in [{'pending':['Q','Q']},{'pending':['W']},{'pending':[]},{'token':'R'},{'pending':['X','Q']}]:
            self.app.submit(event|change);self.assertTrue(self.app.pending.empty())
        self.app.submit(self.event('Ghost Walk','QQW')|{'sequence':['W','Q','R']});self.assertTrue(self.app.pending.empty())

    def test_direct_transport_all_ten_uses_actual_controls(self):
        self.app.keyboard.close();self.app.keyboard=None
        self.app.config.update(transport='direct',input_keys={**self.config['keys'],'select':'2'})
        self.config['input_keys']=self.app.config['input_keys']
        self.app.arm();self.app.tick()
        recipes=json.loads((ROOT/'diseno/mapa-recetas.json').read_text())['spells']
        for recipe in recipes:
            spell=recipe['name'];selectors=recipe['compact'][:-1];prefix=[]
            self.app.receive(self.payload);self.app.cancel_pending();self.app.last_action=None
            self.app.game['abilities']['ability3']['name']='invoker_empty1'
            start=len(self.app.keyboard.events)
            for token in selectors:
                prefix.append(token);self.select(token,prefix)
            def hook(k,v):
                if (k,v)==('r',1):
                    p=deepcopy(self.payload);p['abilities']['ability3']['name']=self.app.spells[spell][1];self.app.receive(p)
            self.app.keyboard.hook=hook
            self.app.submit(self.event(spell,recipe['orbs'])|{'sequence':selectors+['R']});self.app.tick()
            from collections import Counter
            actual=[k for k,v in self.app.keyboard.events[start:] if v and k in {'q','w','e'}]
            self.assertEqual(Counter(actual),Counter(self.config['keys'][o] for o in recipe['orbs']))
            self.assertEqual(self.app.last_action['status'],'observed_in_gsi')
            self.assertFalse({'d','f'} & self.app.keyboard.keys)
            self.app.keyboard.hook=None

    def test_open_chat_blocks_direct_send_and_discards_recipe(self):
        self.app.input_guard.text_blocked=True;self.app.tick()
        self.app.submit(self.event());self.app.tick();self.assertFalse(self.app.keyboard.events)
        self.assertFalse(self.app.context_active);self.assertIn('Chat',self.app.ready()[1])
        self.app.input_guard.text_blocked=False;self.app.tick();self.assertTrue(self.app.context_active)
        self.assertTrue(self.app.pending.empty())

    def test_guards_reject_without_touching_keys(self):
        cases=[('other hero',lambda p:p['hero'].update(name='npc_dota_hero_axe')),('dead',lambda p:p['hero'].update(alive=False)),('silenced',lambda p:p['hero'].update(silenced=True)),('stunned',lambda p:p['hero'].update(stunned=True)),('hexed',lambda p:p['hero'].update(hexed=True)),('paused',lambda p:p['map'].update(paused=True)),('unknown pause',lambda p:p['map'].pop('paused')),('chat',lambda p:p['player'].update(activity='textinput')),('menu',lambda p:p['player'].update(activity='menu')),('spectator',lambda p:p['player'].update(activity='spectating')),('other account',lambda p:p['player'].update(steamid='999')),('loading',lambda p:p['map'].update(game_state='DOTA_GAMERULES_STATE_HERO_SELECTION')),('invoke cooldown',lambda p:p['abilities']['ability5'].update(can_cast=False)),('cooldown inconsistent',lambda p:p['abilities']['ability5'].update(cooldown=1)),('no quas',lambda p:p['abilities']['ability0'].update(level=0)),('missing control state',lambda p:p['hero'].pop('stunned'))]
        for label,change in cases:
            with self.subTest(label=label):
                p=deepcopy(self.payload);change(p);self.app.receive(p);self.app.submit(self.event());self.app.tick()
                self.assertFalse(self.app.keyboard.events);self.assertTrue(self.app.armed)
        self.app.receive(self.payload);self.app.tick();self.focus=False;self.app.submit(self.event());self.assertFalse(self.app.keyboard.events)
    def test_all_modes_use_state_not_match_type(self):
        for mode in ['demo','turbo','all_pick','ranked','custom','bots']:
            p=deepcopy(self.payload);p['map']['gamemode']=mode;self.app.receive(p);self.assertTrue(self.app.ready()[0])
        p['map']['game_state']='DOTA_GAMERULES_STATE_PRE_GAME';self.app.receive(p);self.assertTrue(self.app.ready()[0])
    def test_invalid_or_old_events_and_duplicates_never_dispatch_twice(self):
        for change in [{'timestamp_ms':self.now-501},{'timestamp_ms':self.now+1},{'timestamp_ms':float('nan')},{'timestamp_ms':True},{'spell':'Unknown'},{'orbs':'WWW'},{'orbs':'QQQR'},{'orbs':None},{'type':'accepted'}]:
            self.app.submit(self.event()|change);self.assertTrue(self.app.pending.empty())
        event=self.event();self.confirm_on_invoke('Cold Snap');self.app.submit(event);self.app.tick();count=len(self.app.keyboard.events)
        self.app.submit(event);self.app.tick();self.assertEqual(len(self.app.keyboard.events),count)
    def test_mode_does_not_expire_at_thirty_seconds(self):
        self.advance(31);self.app.receive(self.payload);self.app.tick();self.assertTrue(self.app.armed);self.assertTrue(self.app.context_active)
    def test_stale_gsi_camera_and_modifiers_prevent_output(self):
        self.advance(2);self.assertFalse(self.app.ready()[0]);self.app.submit(self.event());self.assertFalse(self.app.keyboard.events)
        self.app.receive(self.payload);self.app.camera_live=False;self.app.submit(self.event());self.assertFalse(self.app.keyboard.events)
        self.app.camera_live=True;self.app.input_guard.free=False;self.app.submit(self.event());self.assertFalse(self.app.keyboard.events)
    def test_camera_stall_mid_send_aborts_before_invoke(self):
        epoch=self.app.context_generation
        self.app.camera_timestamp_ms=self.now
        self.app.submit(self.event());self.app.tick()
        self.assertNotIn(('f16',1),self.app.keyboard.events)
        self.assertEqual(self.app.last_action['status'],'cancelled');self.assertFalse(self.app.keyboard.down)
        self.assertEqual(self.app.context_generation,epoch)

    def test_prepared_notification_requires_gsi_or_existing_slot_d(self):
        notifications=[];self.app.on_prepared=notifications.append
        self.app.submit(self.event());self.app.tick()
        self.assertEqual(notifications,[])
        p=deepcopy(self.payload);p['abilities']['ability3']['name']='invoker_cold_snap'
        self.app.receive(p);self.app.receive(p)
        self.assertEqual(len(notifications),1);self.assertEqual(notifications[0]['type'],'prepared')
        self.assertEqual(self.app.snapshot()['prepared_events'],notifications)
        self.advance(.05);self.app.submit(self.event());self.app.tick()
        self.assertEqual(self.app.last_action['status'],'already_available');self.assertEqual(len(notifications),2)
        self.assertEqual(notifications[-1]['spell'],'Cold Snap')

    def spell_payload(self,spell='Cold Snap',slot='ability3',cooldown=0):
        p=deepcopy(self.payload);p['abilities'][slot].update(name=self.app.spells[spell][1],cooldown=cooldown)
        return p

    def test_cast_feedback_all_ten_spells_in_either_slot_without_sending_keys(self):
        for spell in self.app.spells:
            for slot in ['ability3','ability4']:
                with self.subTest(spell=spell,slot=slot):
                    p=self.spell_payload(spell,slot);self.advance(.2);self.app.receive(p)
                    before=len(self.app.cast_events);p['abilities'][slot]['cooldown']=20
                    self.advance(.2);self.app.receive(p)
                    self.assertEqual(len(self.app.cast_events),before+1)
                    e=self.app.cast_events[-1];self.assertEqual(e['spell'],spell);self.assertEqual(e['slot'],slot)
                    self.assertEqual(e['evidence'],'cooldown_started')
                    self.app.receive(p);p['abilities'][slot]['cooldown']=19;self.app.receive(p)
                    self.assertEqual(len(self.app.cast_events),before+1)
        self.assertEqual(self.app.keyboard.events,[])

    def test_invoke_slot_swap_cached_spell_and_new_cooldown_do_not_fake_cast(self):
        p=self.spell_payload();self.app.receive(p)
        p['abilities']['ability4']=deepcopy(p['abilities']['ability3'])
        p['abilities']['ability3'].update(name='invoker_emp',cooldown=15)
        self.app.receive(p);self.assertEqual(list(self.app.cast_events),[])
        p['abilities']['ability4']['cooldown']=20;self.app.receive(p)
        self.assertEqual(self.app.cast_events[-1]['spell'],'Cold Snap')

    def test_cast_feedback_consumed_charge_once_even_with_cooldown_already_running(self):
        p=self.spell_payload('Sun Strike',cooldown=10)
        p['abilities']['ability3'].update(charges=2,max_charges=2)
        self.app.receive(p);p['abilities']['ability3'].update(charges=1,cooldown=9)
        self.app.receive(p);self.app.receive(p)
        self.assertEqual(len(self.app.cast_events),1);self.assertEqual(self.app.cast_events[-1]['evidence'],'charge_spent')
        p['abilities']['ability3']['charges']=2;self.app.receive(p)
        self.assertEqual(len(self.app.cast_events),1)

    def test_cast_feedback_ignores_initial_state_rearm_and_stale_history(self):
        p=self.spell_payload(cooldown=20);self.app.receive(p)
        self.assertEqual(list(self.app.cast_events),[])
        self.app.disarm();p['abilities']['ability3']['cooldown']=0;self.app.receive(p)
        self.app.arm();p['abilities']['ability3']['cooldown']=20;self.app.receive(p)
        self.assertEqual(list(self.app.cast_events),[])
        p['abilities']['ability3']['cooldown']=0;self.app.receive(p)
        self.advance(2);p['abilities']['ability3']['cooldown']=20;self.app.receive(p)
        self.assertEqual(list(self.app.cast_events),[])

    def test_cast_feedback_requires_own_live_invoker_active_same_session(self):
        cases=[('hero','name','npc_dota_hero_axe'),('hero','alive',False),('player','steamid','456'),
               ('player','activity','spectating'),('map','paused',True),('map','matchid','2')]
        for section,key,value in cases:
            with self.subTest(key=key,value=value):
                p=self.spell_payload();self.app.receive(p);p[section][key]=value
                p['abilities']['ability3']['cooldown']=20;self.app.receive(p)
                self.assertEqual(list(self.app.cast_events),[])

    def test_no_cast_feedback_for_can_cast_toggle_or_free_spell_with_no_cooldown(self):
        p=self.spell_payload();self.app.receive(p)
        p['abilities']['ability3']['can_cast']=False;self.app.receive(p)
        p['abilities']['ability3']['can_cast']=True;self.app.receive(p)
        self.assertEqual(list(self.app.cast_events),[])
        for cd in [False,-1,float('nan'),float('inf')]:
            p=self.spell_payload();self.app.receive(p);p['abilities']['ability3']['cooldown']=cd;self.app.receive(p)
        self.assertEqual(list(self.app.cast_events),[])

    def test_brief_camera_jitter_preserves_context_but_never_sends_stale_pose(self):
        self.select('E',['E']);self.select('W',['E','W'])
        epoch=self.app.context_generation;progress=deepcopy(self.app.progress)
        self.app.camera_timestamp_ms=self.now;self.advance(.18);self.app.camera_live=False
        self.app.tick()
        self.assertEqual(self.app.context_generation,epoch);self.assertEqual(self.app.progress,progress)
        before=list(self.app.keyboard.events)
        self.app.submit(self.event('Chaos Meteor','EEW')|{'sequence':['E','W','R']});self.app.tick()
        self.assertEqual(self.app.keyboard.events,before)
        self.assertIsNone(self.app.progress)
        # A NEW, fresh confirmation repairs unknown orb state with all three orbs.
        self.app.camera_live=True;self.app.camera_timestamp_ms=None;self.confirm_on_invoke('Chaos Meteor')
        self.advance(.05);self.app.submit(self.event('Chaos Meteor','EEW')|{'sequence':['E','W','R']});self.app.tick()
        self.assertTrue(self.app.last_action['repaired']);self.assertEqual(self.app.last_action['status'],'observed_in_gsi')

    def test_long_camera_loss_or_focus_loss_invalidates_context_immediately(self):
        self.select('E',['E']);epoch=self.app.context_generation
        self.app.camera_timestamp_ms=self.now;self.app.camera_live=False
        self.advance(1.61);self.app.receive(self.payload);self.app.tick()
        self.assertGreater(self.app.context_generation,epoch);self.assertIsNone(self.app.progress)
        self.app.camera_timestamp_ms=None;self.app.camera_live=True;self.app.tick()
        self.select('W',['W']);epoch=self.app.context_generation
        self.focus=False;self.app.tick()
        self.assertGreater(self.app.context_generation,epoch);self.assertIsNone(self.app.progress)
    def test_focus_lost_mid_sequence_releases_keys_without_invoke(self):
        def hook(k,v):
            if k=='f13' and v:self.focus=False
        self.app.keyboard.hook=hook;self.app.submit(self.event());self.app.tick()
        self.assertFalse(self.app.keyboard.down);self.assertNotIn(('f16',1),self.app.keyboard.events)
        self.assertEqual(self.app.last_action['status'],'cancelled');self.assertTrue(self.app.armed)
    def test_session_changed_drops_pending_event(self):
        self.app.submit(self.event());p=deepcopy(self.payload);p['map']['matchid']='2';self.app.receive(p);self.app.tick();self.assertFalse(self.app.keyboard.events)
    def test_recipe_cancel_keeps_mode_enabled_and_drops_old_pending(self):
        self.app.submit(self.event());self.app.cancel_pending('recipe_timeout');self.app.tick()
        self.assertTrue(self.app.armed);self.assertFalse(self.app.keyboard.events)
    def test_binding_change_prevents_send(self):
        self.bindings.write_text(self.bindings.read_text().replace('"q"','"z"'))
        self.app.submit(self.event());self.app.tick();self.assertFalse(self.app.keyboard.events);self.assertEqual(self.app.last_action['status'],'cancelled')
    def use_semantic_controls_check(self):
        from jutsu_invoker.dota import controls_signature
        self.app.config['controls_signature']=controls_signature(self.bindings)
        self.app.config['bindings_sha256']=hashlib.sha256(self.bindings.read_bytes()).hexdigest()
    def test_formatting_and_unrelated_metadata_do_not_disconnect(self):
        self.use_semantic_controls_check()
        self.bindings.write_text(self.bindings.read_text().replace('"KeyBindings" {','"KeyBindings" { "Name" "updated profile" "Version" "12"\n'))
        self.confirm_on_invoke('Cold Snap');self.app.submit(self.event());self.app.tick()
        self.assertTrue(self.app.armed);self.assertEqual(self.app.last_action['status'],'observed_in_gsi')
    def test_unrelated_binding_does_not_disconnect(self):
        self.use_semantic_controls_check()
        self.bindings.write_text(self.bindings.read_text().replace('"Keys" {','"Keys" { "Inventory1" { "Key" "z" }'))
        self.confirm_on_invoke('Cold Snap');self.app.submit(self.event());self.app.tick()
        self.assertTrue(self.app.armed);self.assertEqual(self.app.last_action['status'],'observed_in_gsi')
    def test_semantic_check_still_blocks_new_alternate_cast_on_orb_key(self):
        self.use_semantic_controls_check()
        self.bindings.write_text(self.bindings.read_text().replace('"Keys" {','"Keys" { "AbilitySecondary1QuickCast" { "Key" "q" "Mode" "0" }'))
        self.app.submit(self.event());self.app.tick()
        self.assertFalse(self.app.keyboard.events);self.assertFalse(self.app.armed)
    def test_semantic_check_blocks_other_command_colliding_with_orb_key(self):
        self.use_semantic_controls_check()
        self.bindings.write_text(self.bindings.read_text().replace('"Keys" {','"Keys" { "Attack" { "Key" "q" }'))
        self.app.submit(self.event());self.app.tick()
        self.assertFalse(self.app.keyboard.events);self.assertFalse(self.app.armed)
    def test_semantic_check_blocks_mode_change(self):
        self.use_semantic_controls_check()
        self.bindings.write_text(self.bindings.read_text().replace('"Key" "r"','"Key" "r" "Mode" "1"'))
        self.app.submit(self.event());self.app.tick()
        self.assertFalse(self.app.keyboard.events);self.assertFalse(self.app.armed)
    def test_semantic_check_blocks_hero_override(self):
        self.use_semantic_controls_check()
        self.bindings.write_text(self.bindings.read_text().replace('"Keys" {','"UseHeroBindings" "1" "Units" { "npc_dota_hero_invoker" { "AbilityPrimary1" { "Key" "z" } } } "Keys" {'))
        self.app.submit(self.event());self.app.tick()
        self.assertFalse(self.app.keyboard.events);self.assertFalse(self.app.armed)
    def test_per_hero_units_overrides_are_checked_before_send(self):
        text=self.bindings.read_text()
        text=text.replace('"Keys" {','"UseHeroBindings" "1" "Units" { "npc_dota_hero_invoker" { "AbilityPrimary1" { "Key" "z" } } } "Keys" {')
        self.bindings.write_text(text)
        self.assertEqual(read_controls(self.bindings)['keys']['Q'],'z')
        self.app.submit(self.event());self.app.tick()
        self.assertFalse(self.app.keyboard.events);self.assertFalse(self.app.armed)
    def test_changed_alternate_cast_binding_prevents_orb_key_from_casting(self):
        self.app.config['bindings_sha256']=hashlib.sha256(self.bindings.read_bytes()).hexdigest()
        self.bindings.write_text(self.bindings.read_text().replace('"Keys" {','"Keys" { "AbilitySecondary1QuickCast" { "Key" "q" "Mode" "0" }'))
        self.app.submit(self.event());self.app.tick()
        self.assertFalse(self.app.keyboard.events);self.assertFalse(self.app.armed)
    def test_binding_change_during_send_prevents_invoke(self):
        def hook(k,v):
            if k=='f13' and v:self.bindings.write_text(self.bindings.read_text().replace('"q"','"z"'))
        self.app.keyboard.hook=hook;self.app.submit(self.event());self.app.tick()
        self.assertNotIn(('f16',1),self.app.keyboard.events);self.assertFalse(self.app.armed)
        self.assertFalse(self.app.keyboard.down)
    def test_no_confirmation_disarms_without_retry(self):
        self.app.submit(self.event());self.app.tick();count=len(self.app.keyboard.events)
        self.advance(2);self.app.receive(self.payload);self.app.tick()
        self.assertFalse(self.app.armed);self.assertEqual(self.app.last_action['status'],'unconfirmed');self.assertEqual(len(self.app.keyboard.events),count)
    def test_spell_previously_in_other_slot_is_not_a_new_confirmation(self):
        p=deepcopy(self.payload);p['abilities']['ability4']['name']='invoker_cold_snap';self.app.receive(p)
        self.app.submit(self.event());self.app.tick();self.app.receive(p)
        self.assertEqual(self.app.last_action['status'],'sent_waiting_gsi')
    def test_gsi_rejects_wrong_provider_and_stale_timestamp(self):
        for change in [{'appid':730},{'timestamp':time.time()-5},{'timestamp':float('nan')}]:
            p=deepcopy(self.payload);p['provider'].update(change)
            with self.assertRaises(ValueError):self.app.receive(p)
    def test_keyboard_error_releases_all_pressed_keys(self):
        def broken(seconds):raise OSError('simulated error')
        self.app.sleep=broken;self.app.submit(self.event());self.app.tick()
        self.assertFalse(self.app.keyboard.down);self.assertEqual(self.app.last_action['status'],'cancelled')

    def test_busy_event_preserves_confirmation_and_does_not_replay_later(self):
        self.app.submit(self.event());self.app.tick();count=len(self.app.keyboard.events)
        self.app.submit(self.event('EMP','WWW'))
        self.assertEqual(self.app.last_action['status'],'sent_waiting_gsi');self.assertTrue(self.app.pending.empty())
        p=deepcopy(self.payload);p['abilities']['ability3']['name']='invoker_cold_snap';self.app.receive(p);self.app.tick()
        self.assertEqual(self.app.last_action['status'],'observed_in_gsi');self.assertEqual(len(self.app.keyboard.events),count)
    def test_already_prepared_spell_needs_no_keys(self):
        p=deepcopy(self.payload);p['abilities']['ability3']['name']='invoker_cold_snap';self.app.receive(p)
        self.app.submit(self.event());self.app.tick()
        self.assertFalse(self.app.keyboard.events);self.assertEqual(self.app.last_action['status'],'already_available')
    def test_new_match_cannot_confirm_old_invocation(self):
        self.app.submit(self.event());self.app.tick()
        p=deepcopy(self.payload);p['map']['matchid']='2';p['abilities']['ability3']['name']='invoker_cold_snap';self.app.receive(p)
        self.assertEqual(self.app.last_action['status'],'cancelled')

    def test_pose_before_focus_return_or_previous_context_cannot_dispatch(self):
        old=self.event();self.advance(.1);self.app.cancel_pending('focus returned')
        self.app.submit(old);self.assertTrue(self.app.pending.empty())
        self.app.submit(self.event()|{'dota_context_generation':self.app.context_generation-1})
        self.assertTrue(self.app.pending.empty());self.assertFalse(self.app.keyboard.events)

    def test_changed_slots_never_execute_another_ability(self):
        p=deepcopy(self.payload);p['abilities']['ability5']['name']='invoker_sun_strike';p['abilities']['ability8']=self.payload['abilities']['ability5']
        self.app.receive(p);self.assertFalse(self.app.ready()[0]);self.app.submit(self.event());self.app.tick();self.assertFalse(self.app.keyboard.events)
    def test_modified_input_config_cannot_emit_any_key(self):
        Path(self.config['input_config']).write_text('bind F16 "dota_ability_execute 3"')
        self.app.submit(self.event());self.app.tick();self.assertFalse(self.app.keyboard.events);self.assertEqual(self.app.last_action['status'],'cancelled')


class GsiHttpTests(unittest.TestCase):
    def test_http_token_validation_and_payload_limits(self):
        import http.client
        import threading
        from types import SimpleNamespace
        from jutsu_invoker.dota import GsiServer
        received=[]
        server=GsiServer(SimpleNamespace(config={'gsi_token':'local-test'},receive=received.append),0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            def post(body):
                c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3);c.request('POST','/',body=body)
                r=c.getresponse();status=r.status;r.read();c.close();return status
            self.assertEqual(post(b'{}'),403);self.assertEqual(post(b'{'),400);self.assertEqual(post(b'[]'),400)
            self.assertEqual(post(b'x'*65537),400)
            self.assertEqual(post(b'{"auth":{"token":"local-test"},"provider":{"appid":570}}'),200)
            self.assertEqual(len(received),1)
        finally:server.shutdown();server.server_close();thread.join()

class DotaInstallerTests(unittest.TestCase):
    def test_install_preserves_controls_and_autoexec_is_idempotent(self):
        from jutsu_invoker.dota import install_gsi
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);game=root/'game-install';cfg=game/'game/dota/cfg';cfg.mkdir(parents=True)
            bindings=root/'userdata/123/570/remote/cfg/keys.lst';bindings.parent.mkdir(parents=True)
            roles=dict(AbilityPrimary1='q',AbilityPrimary2='w',AbilityPrimary3='e',AbilityUltimate='r',AbilitySecondary1='d',AbilitySecondary2='f',HeroSelect='2')
            original='"KeyBindings" { "Keys" {'+' '.join(f'"{r}" {{ "Key" "{k}" }}' for r,k in roles.items())+'} }'
            bindings.write_text(original);(cfg/'autoexec.cfg').write_text('echo "existing configuration"\n')
            result=install_gsi(root,game,bindings);install_gsi(root,game,bindings)
            self.assertEqual(bindings.read_text(),original)
            self.assertEqual((cfg/'autoexec.cfg').read_text(),'echo "existing configuration"\n')
            self.assertFalse((cfg/'jutsu_invoker_input.cfg').exists())
            saved=json.loads((root/'runtime/dota/config.json').read_text())
            self.assertEqual(saved['cast_keys'],['d','f']);self.assertEqual(saved['input_keys']['R'],'r');self.assertEqual(saved['transport'],'direct')
    def test_existing_reserved_key_is_never_overwritten(self):
        from jutsu_invoker.dota import install_gsi
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);game=root/'game-install';cfg=game/'game/dota/cfg';cfg.mkdir(parents=True)
            bindings=root/'userdata/123/570/remote/cfg/keys.lst';bindings.parent.mkdir(parents=True)
            roles=dict(AbilityPrimary1='q',AbilityPrimary2='w',AbilityPrimary3='e',AbilityUltimate='r',AbilitySecondary1='d',AbilitySecondary2='f',HeroSelect='2',Inventory1='F13')
            bindings.write_text('"KeyBindings" { "Keys" {'+' '.join(f'"{r}" {{ "Key" "{k}" }}' for r,k in roles.items())+'} }')
            original=bindings.read_text();install_gsi(root,game,bindings)
            self.assertEqual(bindings.read_text(),original)
            self.assertFalse((cfg/'autoexec.cfg').exists());self.assertFalse((cfg/'jutsu_invoker_input.cfg').exists())
