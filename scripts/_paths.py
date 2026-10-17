# -*- coding: utf-8 -*-
"""Shared paths and settings so every script can be run from anywhere."""
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LYRICS = ROOT / 'lyrics'      # local only, never committed (see .gitignore)
DATA = ROOT / 'data'
DIST = ROOT / 'dist'

for d in (DATA, DIST):
    d.mkdir(exist_ok=True)

SONG_LIST = DATA / 'song_list.csv'
COUNTS = DATA / 'counts.json'

# Windows consoles default to cp932/gbk; force UTF-8 so logging never dies on 日本語.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# owner/repo used to build the Yomitan self-update URLs.
# GitHub Actions sets GITHUB_REPOSITORY automatically; override locally with GH_REPO.
GH_REPO = os.environ.get('GITHUB_REPOSITORY') or os.environ.get('GH_REPO') or 'Yisoragoto/jmusic-freq'
GH_BRANCH = os.environ.get('GH_BRANCH', 'main')
ZIP_NAME = 'jmusic-freq.zip'
