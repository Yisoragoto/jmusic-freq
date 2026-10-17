# -*- coding: utf-8 -*-
"""Validate dist/ against Yomitan's official schemas before it is published."""
import json, zipfile, sys, requests
from jsonschema import Draft7Validator
from _paths import DIST, ZIP_NAME

BASE = 'https://raw.githubusercontent.com/yomidevs/yomitan/master/ext/data/schemas/'
SCHEMAS = {
    'index.json': 'dictionary-index-schema.json',
    'term_meta_bank_': 'dictionary-term-meta-bank-v3-schema.json',
}

ok = True
schemas = {k: requests.get(BASE + v, timeout=60).json() for k, v in SCHEMAS.items()}
with zipfile.ZipFile(DIST / ZIP_NAME) as z:
    names = z.namelist()
    print('archive contains:', names)
    if 'index.json' not in names or not any(n.startswith('term_meta_bank_') for n in names):
        print('FAIL archive must hold index.json and at least one term_meta_bank'); ok = False
    for member in names:
        prefix = 'index.json' if member == 'index.json' else 'term_meta_bank_'
        data = json.loads(z.read(member).decode('utf-8'))
        errors = sorted(Draft7Validator(schemas[prefix]).iter_errors(data), key=lambda e: list(e.path))
        count = len(data) if isinstance(data, list) else 1
        if errors:
            ok = False
            print('FAIL %-24s %d error(s)' % (member, len(errors)))
            for e in errors[:5]:
                print('     at', list(e.path)[:4], '->', e.message[:200])
        else:
            print('PASS %-24s %6d item(s)  [%s]' % (member, count, SCHEMAS[prefix]))
    zipped_index = json.loads(z.read('index.json').decode('utf-8'))

# Yomitan compares the revision it finds at indexUrl with the one it already has,
# then downloads downloadUrl. Those two files must agree or updating never settles.
published = json.loads((DIST / 'index.json').read_text(encoding='utf-8'))
if published != zipped_index:
    print('FAIL dist/index.json differs from the index.json inside the archive'); ok = False
else:
    print('PASS dist/index.json matches the archive copy')

for field in ('isUpdatable', 'indexUrl', 'downloadUrl'):
    if field not in published:
        print('FAIL index.json is missing %s — Yomitan self-update disabled' % field); ok = False
if published.get('downloadUrl', '').rsplit('/', 1)[-1] != ZIP_NAME:
    print('FAIL downloadUrl does not point at %s' % ZIP_NAME); ok = False

print('\nrevision:', published.get('revision'))
print('ALL CHECKS PASS' if ok else 'VALIDATION FAILED')
sys.exit(0 if ok else 1)
