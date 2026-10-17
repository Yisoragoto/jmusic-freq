# -*- coding: utf-8 -*-
"""Tokenize local lyrics (lyrics/<id>.txt) and write aggregate counts to data/counts.json.

Only counts leave this script: per lemma, how many songs and artists use it, the
total token count, and which written forms appeared. No lines, no word order —
nothing that could rebuild a lyric — so counts.json is safe to publish.

Run locally; lyrics never go to GitHub.
"""
import argparse, collections, csv, json, re, sys, unicodedata
import fugashi
from _paths import LYRICS, SONG_LIST, COUNTS

ap = argparse.ArgumentParser()
ap.add_argument('--genre', help='only count these genres, comma separated (e.g. anime,vocaloid)')
args = ap.parse_args()
genres_wanted = set(args.genre.split(',')) if args.genre else None

# 運命(さだめ) / 想い(おもい): drop the ruby so the tokenizer sees the plain kanji.
RUBY = re.compile(r'(?<=[一-鿿々〆ヵヶ])\([ぁ-ゖァ-ヺー]+\)')
# Leftover ASCII annotations such as (×2) or [Chorus].
ANNOTATION = re.compile(r'[\(\[][^\)\]]*[\)\]]')
HAS_JA = re.compile(r'[ぁ-ゖァ-ヺ一-鿿々]')
SKIP_POS = {'補助記号', '空白', '記号'}
KANA = re.compile(r'^[ぁ-ゖァ-ヺー]+$')

def clean(text):
    text = unicodedata.normalize('NFKC', text)
    text = RUBY.sub('', text)
    text = ANNOTATION.sub(' ', text)
    return text

def hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)

tagger = fugashi.Tagger()

def tokens(text):
    """Yield (lemma, reading, written base form) for every Japanese word in text."""
    for line in text.splitlines():
        if not HAS_JA.search(line):
            continue                           # pure English / romaji line
        for w in tagger(line):
            f = w.feature
            if f.pos1 in SKIP_POS or not HAS_JA.search(w.surface):
                continue
            lemma = getattr(f, 'lemma', None)
            if w.is_unk or not lemma or lemma == '*':
                # Unknown word: keep it only if it is kana (onomatopoeia, slang),
                # because without a dictionary we cannot know a kanji word's reading.
                if KANA.match(w.surface):
                    yield w.surface, hira(w.surface), w.surface
                continue
            # UniDic disambiguates lemmas with a suffix: ベビー-baby, 君-代名詞.
            lemma = re.sub(r'(?<=.)-.*$', '', lemma)
            reading = hira(f.lForm) if f.lForm and f.lForm != '*' else hira(w.surface)
            base = f.orthBase if f.orthBase and f.orthBase != '*' else w.surface
            yield lemma, reading, base

songs = list(csv.DictReader(SONG_LIST.open(encoding='utf-8')))
groups = collections.defaultdict(lambda: {'count': 0, 'songs': set(), 'artists': set(),
                                          'forms': collections.Counter()})
used, missing = [], []
for s in songs:
    if genres_wanted and s['genre'] not in genres_wanted:
        continue
    path = LYRICS / (s['id'] + '.txt')
    if not path.exists():
        missing.append(s['id'])
        continue
    used.append(s)
    for lemma, reading, base in tokens(clean(path.read_text(encoding='utf-8'))):
        g = groups[(lemma, reading)]
        g['count'] += 1
        g['songs'].add(s['id'])
        g['artists'].add(s['artist'])
        g['forms'][base] += 1

if missing:
    print('WARN %d song(s) in song_list.csv have no lyrics file: %s%s'
          % (len(missing), ', '.join(missing[:10]), ' …' if len(missing) > 10 else ''))
if not used:
    sys.exit('no lyrics found in %s' % LYRICS)

words = [{'lemma': lemma, 'reading': reading, 'songs': len(g['songs']),
          'artists': len(g['artists']), 'count': g['count'],
          'forms': dict(sorted(g['forms'].items(), key=lambda kv: (-kv[1], kv[0])))}
         for (lemma, reading), g in sorted(groups.items())]
meta = {
    'songs': len(used),
    'artists': len({s['artist'] for s in used}),
    'genres': dict(sorted(collections.Counter(s['genre'] for s in used).items())),
    'genre_filter': sorted(genres_wanted) if genres_wanted else None,
    'tokenizer': 'fugashi %s + unidic-lite' % fugashi.__version__ if hasattr(fugashi, '__version__')
                 else 'fugashi + unidic-lite',
}

# One word per line so git diffs of counts.json stay readable.
def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
COUNTS.write_text('{"meta":%s,\n"words":[\n%s\n]}\n'
                  % (dumps(meta), ',\n'.join(dumps(w) for w in words)),
                  encoding='utf-8', newline='\n')

print('songs    : %d  artists: %d  genres: %s' % (meta['songs'], meta['artists'], meta['genres']))
print('lemmas   : %d  tokens: %d' % (len(words), sum(w['count'] for w in words)))
print('wrote    :', COUNTS)
