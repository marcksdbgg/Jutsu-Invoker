"""Validated, atomic user overrides; machine configuration stays in TOML."""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import tempfile

# key: section, TOML name, minimum, maximum, kind
FIELDS = {
    'timeout_ms': ('acceptance','inter_sign_timeout_ms',400,10000,int),
    'monkey_score': ('acceptance','monkey_enter_score',.6,.99,float),
    'monkey_stable_ms': ('acceptance','monkey_min_stable_ms',50,1000,int),
    'monkey_observations': ('acceptance','monkey_min_fresh_observations',2,30,int),
    'element_score': ('acceptance','enter_score',.6,.99,float),
    'element_stable_ms': ('acceptance','element_min_stable_ms',50,1000,int),
    'element_observations': ('acceptance','element_min_fresh_observations',2,30,int),
    'confirmation_stable_ms': ('acceptance','confirmation_min_stable_ms',66,1000,int),
    'confirmation_observations': ('acceptance','confirmation_min_fresh_observations',3,30,int),
    'class_margin': ('acceptance','class_margin',0,.5,float),
    'release_ms': ('acceptance','release_min_ms',33,500,int),
    'max_age_ms': ('acceptance','max_observation_age_ms',50,250,int),
    'max_gap_ms': ('acceptance','max_observation_gap_ms',66,500,int),
    'pose_hz': ('vision','pose_diagnostic_hz',0,30,int),
    'preview_fps': ('ui','preview_target_fps',15,30,int),
    'preview_buffer_ms': ('ui','preview_buffer_ms',0,200,int),
    'tiger_refinement': ('vision','tiger_refinement_enabled',None,None,bool),
    'tiger_score': ('vision','tiger_refinement_min_score',.8,.99,float),
    'orientation': ('capture','capture_orientation_degrees',0,270,int),
}


def validate(values):
    if not isinstance(values,dict) or set(values)-FIELDS.keys():
        raise ValueError('Ajustes desconocidos')
    result = {}
    for key,value in values.items():
        _,_,lo,hi,kind = FIELDS[key]
        if kind is bool:
            if type(value) is not bool:raise ValueError(f'{key}: usa sí o no')
        else:
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                raise ValueError(f'{key}: número inválido')
            if not lo <= value <= hi or (kind is int and value != int(value)):
                raise ValueError(f'{key}: usa un valor entre {lo} y {hi}')
            value = kind(value)
        if key=='orientation' and value not in {0,90,180,270}:
            raise ValueError('Giro: usa 0, 90, 180 o 270 grados')
        result[key] = value
    return result


class UserSettings:
    def __init__(self,root:Path,base:dict):
        self.base = deepcopy(base)
        self.path = root/'config/usuario.json'
        self.defaults = {key:base[section][name] for key,(section,name,*_) in FIELDS.items()}
        self.values = self.defaults.copy()
        if self.path.exists():
            self.values.update(validate(json.loads(self.path.read_text())))

    def config(self,values=None):
        result=deepcopy(self.base)
        for key,value in (self.values if values is None else values).items():
            section,name,*_=FIELDS[key];result[section][name]=value
        return result

    def save(self,changes=None,reset=False):
        values=self.defaults.copy() if reset else self.values | validate(changes)
        fd,name=tempfile.mkstemp(prefix='.usuario-',suffix='.json',dir=self.path.parent)
        try:
            with os.fdopen(fd,'w') as f:
                json.dump(values,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
            os.replace(name,self.path)
        finally:
            if os.path.exists(name):os.unlink(name)
        self.values=values
        return values.copy()
