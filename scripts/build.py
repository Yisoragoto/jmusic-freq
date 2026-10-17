# -*- coding: utf-8 -*-
"""Turn data/counts.json into a Yomitan (format 3) frequency dictionary in dist/.

Ranking: a word's rank is decided by how many *songs* use it (document
frequency), then how many artists, then the raw token count. Ranking by songs
keeps a chorus that repeats one word twenty times from inflating it.

Every written form seen in the lyrics (and the UniDic lemma itself) receives the
rank of its lemma group, so 君/きみ/キミ all share one rank and Yomitan finds it
whichever spelling the user hovers.

The build is deterministic: identical counts give byte-identical output, so a
rebuild only produces a git diff (and a Yomitan update) when the data moved.
"""
import argparse, json, re, hashlib, zipfile, datetime
from _paths import COUNTS, DIST, GH_REPO, GH_BRANCH, ZIP_NAME

TITLE = 'JMusic Freq'
BANK_SIZE = 10000
KANA_ONLY = re.compile(r'^[ぁ-ゟ゠-ヿー・]+$')

RAW_BASE = 'https://raw.githubusercontent.com/%s/%s/dist/' % (GH_REPO, GH_BRANCH)
INDEX_URL = RAW_BASE + 'index.json'
DOWNLOAD_URL = RAW_BASE + ZIP_NAME

ap = argparse.ArgumentParser()
ap.add_argument('--min-songs', type=int, default=2,
                help='drop words used in fewer songs than this (default 2)')
args = ap.parse_args()

counts = json.loads(COUNTS.read_text(encoding='utf-8'))
meta, words = counts['meta'], counts['words']

kept = [w for w in words if w['songs'] >= args.min_songs]
kept.sort(key=lambda w: (-w['songs'], -w['artists'], -w['count'], w['lemma'], w['reading']))

def freq_entry(form, reading, rank):
    value = {'value': rank, 'displayValue': str(rank)}
    # A kana-only headword is matched without a reading: JMdict gives katakana
    # words a katakana reading, so pinning a hiragana one here would never match.
    if KANA_ONLY.match(form):
        return [form, 'freq', value]
    return [form, 'freq', {'reading': reading, 'frequency': value}]

# (form, reading) -> best rank; one form can come from several lemma groups.
best = {}
for rank, w in enumerate(kept, 1):
    for form in [w['lemma'], *w['forms']]:
        key = (form, '' if KANA_ONLY.match(form) else w['reading'])
        if key not in best or rank < best[key]:
            best[key] = rank

metas = [freq_entry(form, reading, rank)
         for (form, reading), rank in sorted(best.items(), key=lambda kv: (kv[1], kv[0]))]

def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))

banks = {'term_meta_bank_%d.json' % (i // BANK_SIZE + 1): dumps(metas[i:i + BANK_SIZE])
         for i in range(0, len(metas), BANK_SIZE)}

# --- revision: derived from content, so it only moves when the content moves ---
digest = hashlib.sha256(''.join(banks[k] for k in sorted(banks)).encode('utf-8')).hexdigest()[:12]
revision = 'jmf-%s-%s' % (datetime.date.today().isoformat(), digest)
old_index = DIST / 'index.json'
if old_index.exists():
    prev = json.loads(old_index.read_text(encoding='utf-8')).get('revision', '')
    if prev.endswith('-' + digest):
        revision = prev          # unchanged content keeps its original revision + date

genres = '、'.join('%s %d' % (g, n) for g, n in sorted(meta['genres'].items(), key=lambda kv: -kv[1]))
index = {
    'title': TITLE,
    'format': 3,
    'revision': revision,
    'author': GH_REPO.split('/')[0],
    'url': 'https://github.com/' + GH_REPO,
    'description': (
        '日本語の歌詞 %d 曲（%d アーティスト）から作成した頻度辞書。\n'
        '順位は「その語が使われている曲数」で決まり、サビの繰り返しで水増しされません。\n'
        'ジャンル内訳：%s\n'
        'Frequency list built from %d Japanese songs, ranked by number of songs using each word.'
        % (meta['songs'], meta['artists'], genres, meta['songs'])),
    'attribution': 'Lyrics are not redistributed; only aggregate word counts are published.',
    'sourceLanguage': 'ja',
    'targetLanguage': 'ja',
    'frequencyMode': 'rank-based',
    'isUpdatable': True,
    'indexUrl': INDEX_URL,
    'downloadUrl': DOWNLOAD_URL,
}

files = {'index.json': dumps(index), **banks}
for stale in DIST.glob('term_meta_bank_*.json'):
    stale.unlink()
(DIST / 'index.json').write_text(files['index.json'], encoding='utf-8', newline='\n')

# Fixed timestamps keep the archive byte-identical across rebuilds.
with zipfile.ZipFile(DIST / ZIP_NAME, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for name in sorted(files):
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        info.create_system = 3   # pin to UNIX: the default is platform-dependent
                                 # (0 on Windows) and would otherwise change the bytes
        z.writestr(info, files[name].encode('utf-8'))

print('revision :', revision)
print('lemmas   : %d kept of %d (min songs %d)' % (len(kept), len(words), args.min_songs))
print('entries  : %d in %d bank(s)' % (len(metas), len(banks)))
print('top 20   :', ' '.join('%s(%d)' % (w['lemma'], w['songs']) for w in kept[:20]))
print('indexUrl :', INDEX_URL)
print('zip      : dist/%s (%d bytes)' % (ZIP_NAME, (DIST / ZIP_NAME).stat().st_size))
