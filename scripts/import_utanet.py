# -*- coding: utf-8 -*-
"""Import lyrics from public Hugging Face datasets into lyrics/ + data/song_list.csv.

Sources (all scraped from Uta-Net by their authors, downloaded into sources/):
  KaraKaraWitch/uta-net-songs           ~331k songs with lyrics, up to 2023-03 (main corpus)
  KaraKaraWitch/uta-net-rank-25-05-2024 Uta-Net top 11,700 by page views (song selection)
  mohamed-khalil/AnimeSongsLyrics       ~23k anime songs with Uta-Net URLs (genre: anime)

Lyrics only ever land in sources/ and lyrics/, both git-ignored. song_list.csv
(title / artist / year / genre / rank) is metadata and is committed.

  python scripts/import_utanet.py              # ranked songs only (default)
  python scripts/import_utanet.py --top 5000   # top 5000 of the ranking
  python scripts/import_utanet.py --all        # every song in uta-net-songs

Set HF_ENDPOINT (e.g. https://hf-mirror.com) if huggingface.co is slow.
"""
import argparse, csv, hashlib, json, os, re, unicodedata
import requests
import pyarrow.parquet as pq
from _paths import ROOT, DATA, LYRICS, SONG_LIST

SOURCES = ROOT / 'sources'
HF = os.environ.get('HF_ENDPOINT', 'https://huggingface.co').rstrip('/')
FILES = {
    'songs.jsonl': 'KaraKaraWitch/uta-net-songs/resolve/main/songs.jsonl',
    'UtaNetRank.csv': 'KaraKaraWitch/uta-net-rank-25-05-2024/resolve/main/UtaNetRank.csv',
    'AnimeSongsLyrics.parquet': 'mohamed-khalil/AnimeSongsLyrics/resolve/main/data/AnimeSongsLyrics.parquet',
}

# Singing voice synthesizers as they appear in Uta-Net artist credits ("〇〇 feat. 初音ミク").
# Names that are unambiguous anywhere in the credit...
VOICEBANK = (r'初音ミク|鏡音リン|鏡音レン|巡音ルカ|神威がくぽ|結月ゆかり|重音テト|可不|裏命|星界|知声|'
             r'弦巻マキ|東北きりたん|東北ずん子|ずんだもん|音街ウナ|紲星あかり|歌愛ユキ|小春六花|夏色花梨|'
             r'花隈千冬|v\s?flower')
# ...and short ones that are also real artists (Meiko, ONE OK ROCK, Flower, MARIA),
# which only count right after "feat." / "ft.".
AMBIGUOUS = r'MEIKO|KAITO|GUMI|IA|ONE|flower|VY[12]'
VOCALOID = re.compile(r'%s|(?:feat\.?|ft\.)\s*(?:%s)\b' % (VOICEBANK, AMBIGUOUS), re.I)
ANIME_TIEUP = re.compile(r'アニメ|劇場版')

ap = argparse.ArgumentParser()
ap.add_argument('--all', action='store_true', help='import every song, not only ranked ones')
ap.add_argument('--top', type=int, help='only the top N of the Uta-Net ranking')
args = ap.parse_args()

def download(name, path, attempts=10):
    """Stream a file into sources/, resuming the partial download after every dropped connection.

    Gives up only after `attempts` drops in a row that made no progress at all."""
    out = SOURCES / name
    if out.exists():
        return out
    part = out.with_suffix(out.suffix + '.part')
    attempt, last_size = 0, -1
    while True:
        have = part.stat().st_size if part.exists() else 0
        attempt = 0 if have > last_size else attempt + 1
        last_size = have
        if attempt >= attempts:
            raise SystemExit('download of %s kept failing; re-run to resume' % name)
        headers = {'Range': 'bytes=%d-' % have} if have else {}
        try:
            with requests.get('%s/datasets/%s' % (HF, path), headers=headers, stream=True, timeout=60) as r:
                if r.status_code == 416:                # already complete
                    break
                r.raise_for_status()
                if have and r.status_code != 206:
                    have = 0                            # server ignored Range: start over
                total = have + int(r.headers.get('Content-Length', 0))
                with part.open('ab' if have else 'wb') as f:
                    done, shown = have, have
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                        done += len(chunk)
                        if done - shown >= 50 << 20:
                            print('  %s %d / %d MB' % (name, done >> 20, total >> 20), flush=True)
                            shown = done
            if part.stat().st_size < total:
                print('  %s: stream ended early, resuming' % name, flush=True)
                continue
            break
        except (requests.ConnectionError, requests.Timeout,
                requests.exceptions.ChunkedEncodingError) as e:
            print('  %s: connection dropped (%s), resuming' % (name, type(e).__name__), flush=True)
    part.rename(out)
    return out

def norm(s):
    """Key for matching titles/artists across datasets."""
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', s or '')).lower()

SOURCES.mkdir(exist_ok=True)
paths = {}
for name, path in FILES.items():
    print('fetch   :', name)
    paths[name] = download(name, path)

# --- ranking: (title, artist) -> best rank ---
rank_of = {}
with paths['UtaNetRank.csv'].open(encoding='utf-8-sig') as f:   # the file starts with a BOM
    for row in csv.DictReader(f):
        key = (norm(row['Title']), norm(row['Artist']))
        r = int(row['Rank'])
        if key not in rank_of or r < rank_of[key]:
            rank_of[key] = r

# --- anime: Uta-Net song ids that AnimeSongsLyrics lists ---
urls = pq.read_table(paths['AnimeSongsLyrics.parquet'], columns=['SongURL']).column('SongURL').to_pylist()
anime_ids = {m.group(1) for u in urls if u for m in [re.search(r'/song/(\d+)', u)] if m}

# Producers credited by name alone (DECO*27, wowaka, …): an editable exact-name list.
VOCALOID_LIST = DATA / 'vocaloid_artists.txt'
vocaloid_artists = set()
if VOCALOID_LIST.exists():
    vocaloid_artists = {norm(l) for l in VOCALOID_LIST.read_text(encoding='utf-8').splitlines()
                        if l.strip() and not l.startswith('#')}

def genre(song):
    if VOCALOID.search(song['artist'] or '') or norm(song['artist']) in vocaloid_artists:
        return 'vocaloid'
    if song['id'] in anime_ids or ANIME_TIEUP.search(song.get('tieup') or ''):
        return 'anime'
    return 'general'

# --- select songs, de-duplicating identical lyrics (re-releases, covers, versions) ---
chosen, seen_lyrics = {}, {}
dupes = empty = 0
with paths['songs.jsonl'].open(encoding='utf-8') as f:
    for line in f:
        s = json.loads(line)
        rank = rank_of.get((norm(s['title']), norm(s['artist'])))
        if not args.all and (rank is None or (args.top and rank > args.top)):
            continue
        lyrics = (s.get('lyrics') or '').strip()
        if not lyrics:
            empty += 1
            continue
        digest = hashlib.sha1(norm(lyrics).encode('utf-8')).hexdigest()
        keep = seen_lyrics.get(digest)
        if keep is not None:
            dupes += 1
            old = chosen[keep]
            # Prefer the better-ranked entry, then the earliest release.
            if (rank or 10**9, s.get('release') or '9') >= (old['rank'] or 10**9, old['release'] or '9'):
                continue
            del chosen[keep]
        seen_lyrics[digest] = s['id']
        chosen[s['id']] = {'id': s['id'], 'title': s['title'], 'artist': s['artist'],
                           'release': s.get('release') or '', 'rank': rank,
                           'genre': genre(s), 'lyrics': lyrics}

# --- write lyrics/ (local only) and song_list.csv (published) ---
LYRICS.mkdir(exist_ok=True)
wanted = {'utanet-%s.txt' % i for i in chosen}
stale = [p for p in LYRICS.glob('*.txt') if p.name not in wanted]
for p in stale:
    p.unlink()
for i, s in chosen.items():
    p = LYRICS / ('utanet-%s.txt' % i)
    if not p.exists():
        p.write_text(s['lyrics'], encoding='utf-8', newline='\n')

songs = sorted(chosen.values(), key=lambda s: (s['rank'] or 10**9, int(s['id'])))
with SONG_LIST.open('w', encoding='utf-8', newline='') as f:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['id', 'title', 'artist', 'year', 'genre', 'rank'])
    for s in songs:
        w.writerow(['utanet-' + s['id'], s['title'], s['artist'], s['release'][:4],
                    s['genre'], s['rank'] or ''])

genres = {}
for s in songs:
    genres[s['genre']] = genres.get(s['genre'], 0) + 1
print('ranked  : %d ranking rows, %d anime ids' % (len(rank_of), len(anime_ids)))
print('songs   : %d imported (%d duplicate lyrics, %d empty skipped, %d stale files removed)'
      % (len(songs), dupes, empty, len(stale)))
print('genres  :', genres)
print('wrote   :', SONG_LIST)
