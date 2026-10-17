# JMusic Freq — 日语音乐歌词词频辞典（Yomitan）

基于日语歌词统计的 [Yomitan](https://yomitan.wiki/) 词频辞典（format 3, rank-based）。
覆盖 J-POP、动漫歌曲、VOCALOID、偶像、摇滚、演歌、说唱等各类日语音乐。

> 本仓库**不包含任何歌词**。歌词只在维护者本地处理，公开的只有统计后的词频数据
> （`data/counts.json`）和歌单元数据（`data/song_list.csv`）。

## 安装

Yomitan 设置 → **Dictionaries** → **Import**，填入：

```
https://raw.githubusercontent.com/Yisoragoto/jmusic-freq/main/dist/jmusic-freq.zip
```

辞典声明了 `isUpdatable`，之后在 Dictionaries 页点 **Check for updates** 即可自动更新。

## 统计方法

| 项目 | 说明 |
|---|---|
| 分词 | [fugashi](https://github.com/polm/fugashi) + UniDic（unidic-lite） |
| 归并 | 按 UniDic 的 lemma + 读音归并，活用形还原为辞书形（食べた → 食べる） |
| 排名 | **使用该词的歌曲数** → 使用该词的歌手数 → 总出现次数。副歌重复不会抬高排名 |
| 写法 | 歌词里出现过的每种写法（君 / きみ / キミ）都收录，共享同一排名 |
| 过滤 | 去掉符号、英文、数字；歌词里的ルビ括号（`運命(さだめ)`）会先剥掉 |
| 门槛 | 默认只收录至少出现在 2 首歌里的词（`build.py --min-songs`） |

收录的歌曲列表见 [`data/song_list.csv`](data/song_list.csv)，流派分布写在辞典的描述里。

## 数据来源

| 数据集 | 用途 |
|---|---|
| [KaraKaraWitch/uta-net-songs](https://huggingface.co/datasets/KaraKaraWitch/uta-net-songs) | 主语料：歌ネット约 33 万首歌（截至 2023-03） |
| [KaraKaraWitch/uta-net-rank-25-05-2024](https://huggingface.co/datasets/KaraKaraWitch/uta-net-rank-25-05-2024) | 选曲：歌ネット总榜前 11,700 首（按页面访问量） |
| [mohamed-khalil/AnimeSongsLyrics](https://huggingface.co/datasets/mohamed-khalil/AnimeSongsLyrics) | 流派：按歌ネット曲目 ID 标出动漫歌曲 |

默认只收录排行榜上的歌，歌词完全相同的版本（重新发行、翻唱）只算一次。流派分三类：

- `vocaloid`：歌手栏写有合成音声（`feat. 初音ミク` 等）
- `anime`：出现在 AnimeSongsLyrics 里，或 tie-up 栏含「アニメ」「劇場版」
- `general`：其余所有歌曲

数据截至 2023 年 3 月，不含角色歌和同人作品。

## 本地生成

```bash
pip install fugashi unidic-lite requests jsonschema pyarrow
```

1. 导入歌词（首次会下载约 1GB 到 `sources/`；`sources/` 和 `lyrics/` 都已被 `.gitignore` 忽略）：

```bash
python scripts/import_utanet.py              # 排行榜上的歌（默认）
python scripts/import_utanet.py --top 5000   # 只要排行榜前 5000
python scripts/import_utanet.py --all        # 全部约 33 万首
```

   连 huggingface.co 慢的话，可以设 `HF_ENDPOINT=https://hf-mirror.com`。
   也可以不导入，手动在 `data/song_list.csv` 登记歌曲，并把歌词存成 `lyrics/<id>.txt`。

2. 统计并构建：

```bash
python scripts/count_words.py   # lyrics/ → data/counts.json（可加 --genre anime 只统计某流派）
python scripts/build.py         # counts.json → dist/index.json + dist/jmusic-freq.zip
python scripts/validate.py      # 用 Yomitan 官方 schema 校验
```

3. 提交 `data/` 和 `dist/` 后 push。GitHub Actions 会从 `counts.json` 重新构建并校验，
   如果提交的 `dist/` 和重新构建的结果不一致，检查会失败。

构建是可复现的：`revision` 由内容的 SHA-256 推出，zip 内时间戳固定，
所以数据没变时重新构建不会产生 diff，Yomitan 也不会收到空更新。

fork 后请用 `GH_REPO=owner/repo python scripts/build.py` 构建，让更新链接指向你自己的仓库
（CI 里会自动读取 `GITHUB_REPOSITORY`）。

## 权利

- 代码：MIT
- 词频数据（`data/counts.json`、`dist/`）：CC BY-SA 4.0
- 歌词著作权归各权利人所有。本项目只发布聚合后的词频统计，不发布歌词文本或可还原歌词的数据。
  如有异议请提 issue。
