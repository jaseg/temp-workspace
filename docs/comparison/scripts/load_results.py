"""Load the five final result JSONs into {impl: {name: result}} and helpers to classify cases by family."""
import json
B = __import__('os').environ.get('KICOIL_BENCH', __import__('os').environ.get('KICOIL_BENCH', '/tmp/claude-0/bench/final')).rstrip('/') + '/'
FILES = {'original': 'original_full.json', 'fixed': 'kicoil_full.json', 'cornerflat': 'cornerflat_full.json',
         'optspan': 'geometry_alt_optspan_full.json', 'jog': 'geometry_alt_jog_full.json'}
IMPLS = list(FILES)

def load():
    return {k: {r['name']: r for r in json.load(open(B + f))} for k, f in FILES.items()}

def family(r):
    t = r.get('tags', [])
    n = r['name']
    if 'round' in t:
        return 'round'
    if 'concave' in t:
        return 'concave'
    return 'main'

def label(r):
    if r is None:
        return 'missing'
    s = r['status']
    if s == 'fail':
        return 'fail: ' + ', '.join(r.get('failures', []))
    return s
