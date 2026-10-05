"""Verifica recetas y gramática pura. No accede a cámara, red ni teclado."""
from collections import Counter
from itertools import product, permutations
import json
from pathlib import Path

root = Path(__file__).resolve().parent
spec = json.loads((root / 'mapa-recetas.json').read_text())

def signature(orbs):
    return tuple(orbs.count(k) for k in 'QWE')

def decode_compact(tokens):
    if not tokens or tokens[-1] != 'R' or 'R' in tokens[:-1]:
        raise ValueError('Falta confirmación final única')
    body = tokens[:-1]
    if any(x not in 'QWE' for x in body):
        raise ValueError('Elemento desconocido')
    if len(body) == 1:
        return signature(body * 3)
    if len(body) == 2 and len(set(body)) == 2:
        return signature([body[0], body[0], body[1]])
    if len(body) == 3 and len(set(body)) == 3:
        return (1, 1, 1)
    raise ValueError('Fórmula inválida')

expected = {
    (3,0,0): 'Cold Snap', (2,1,0): 'Ghost Walk', (2,0,1): 'Ice Wall',
    (0,3,0): 'EMP', (1,2,0): 'Tornado', (0,2,1): 'Alacrity',
    (0,0,3): 'Sun Strike', (1,0,2): 'Forge Spirit',
    (0,1,2): 'Chaos Meteor', (1,1,1): 'Deafening Blast',
}
counts = Counter(signature(list(s)) for s in product('QWE', repeat=3))
assert len(counts) == 10 and sum(counts.values()) == 27
assert set(counts) == set(expected)
assert sorted(counts.values()) == [1,1,1,3,3,3,3,3,3,6]
assert len(spec['spells']) == 10
assert len({s['name'] for s in spec['spells']}) == 10
for s in spec['spells']:
    key = signature(s['orbs'])
    assert expected[key] == s['name']
    assert key == tuple(s['counts'][k] for k in 'QWE')
    assert decode_compact(s['compact']) == key
    assert s['literal'] == list(s['orbs'] + 'R')
for perm in permutations('QWE'):
    assert decode_compact(list(perm) + ['R']) == (1,1,1)
accepted = []
for size in range(5):
    for word in product('QWE', repeat=size):
        try:
            accepted.append((word, decode_compact(list(word) + ['R'])))
        except ValueError:
            pass
assert len(accepted) == 15  # 3 puras + 6 dominantes + 6 órdenes de equilibrio
assert len({v for _, v in accepted}) == 10
for tokens in [[], ['R'], list('QQR'), list('QWRR'), list('QWE'), list('XR'), list('QWERQ')]:
    try:
        decode_compact(tokens)
    except ValueError:
        continue
    raise AssertionError(f'Se aceptó una fórmula inválida: {tokens}')
assert sum(len(s['compact']) for s in spec['spells']) / 10 == 2.8
print('Correcto: 27 cadenas literales → 10 recetas.')
print('Correcto: multiplicidades 3×1 + 6×3 + 1×6 = 27.')
print('Correcto: 10 fórmulas canónicas compactas → las mismas 10 recetas.')
print('Correcto: 15 secuencias compactas aceptadas al admitir 6 permutaciones de QWE.')
print('Correcto: todas requieren confirmación final; entradas inválidas rechazadas.')
print('Media uniforme de eventos de sello compactos, incluida serpiente: 2.8.')
print('No valida cámara, detección temporal, rendimiento, Dota ni condiciones de uso.')
