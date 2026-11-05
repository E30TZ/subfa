# Changelog

All notable changes to SubFa are documented here.

## [0.2.0] - 2026-11-05

### Added
- One-line install for every platform (PasarGuard style): a hosted
  install script that clones the project itself, then runs an
  interactive wizard (1 bot, 2 web, 3 CLI) or takes flags
  (`install --target bot --token ... --admin-id ...`). The bot branch
  validates the token live; the web branch offers a domain with
  nginx and Let's Encrypt, or serving on the machine's IP, and can
  register a systemd service on Linux VPS. This is now the primary
  install method in the README; the full manual path lives in
  docs/INSTALL.md.
- Official logo and brand asset set (caption-block mark): vector
  masters, PNG sizes, bot avatar, favicons, GitHub social preview,
  and docs/BRAND.md with construction and usage rules.
- Optional LLM translation provider (`SUBFA_TRANSLATOR=llm` plus an
  OpenAI-compatible base URL, key, and model): context-window
  translation with strict ordering, automatic per-chunk fallback to
  the offline Argos provider. The provider used is recorded in each
  job report.
- Video quality selection (source, 720, 480, 360) and subtitle tone
  selection (auto, formal, informal, simple) on the bot, the web
  app, and the CLI.

### Changed
- Video-first delivery: whenever the source media exists, the
  burned-in subtitled video is the primary result on all three
  surfaces, with the SRT files alongside it.
- Burned-in subtitles are now resolution-aware (font size scales
  with the real frame height) and render in the bundled Vazirmatn
  typeface on every host, so they stay large and readable at 360p.
- Source text preference: published captions, then real ASR
  transcription when only automatic captions exist, then cleaned
  automatic captions. Rolling auto captions are repaired (overlap
  removed, sentences rebuilt) before translation.
- YouTube: when the standard download routes are gated, the
  downloader falls back to the Android player client, which still
  serves a 360p media file, so YouTube links now also produce the
  burned-in video instead of subtitle files only.

### Fixed
- ffmpeg 8 filter parsing for the subtitle burn on macOS and
  Windows (named filename option, relative fonts directory, no
  absolute paths inside the filter chain), with a clear error when
  an ffmpeg build lacks the libass subtitle filter.
- CI is green on Ubuntu, Windows, and macOS.

## [0.1.0] - 2026-11-05

First public release.

### Added
- Subtitle pipeline: media file or video link in; target-language SRT
  (Persian by default), bilingual SRT, plain transcript, and a
  burned-in video copy out.
- Three entry points: Telegram bot, web app with a subtitle cue
  editor, and CLI.
- Link input via yt-dlp with a captions fast path and automatic
  speech-recognition fallback.
- Language-aware speech recognition: Persian audio is routed to a
  Persian fine-tuned model (`nezamisafa/whisper-persian-v4`, top of
  the PESTE benchmark); other languages use faster-whisper
  `large-v3-turbo` with anti-hallucination decoding. Decision record
  and benchmark harness included (`docs/ASR.md`,
  `tools/benchmark_asr.py`).
- Offline-first model delivery: `subfa download-models`, Docker
  `BUNDLE_MODELS=1`, `HF_ENDPOINT` mirror support.
- Offline translation with Argos Translate; modular JSON glossaries
  (general, programming, gaming).
- Subtitle craft rules: at most 2 lines and 42 characters per line,
  reading-speed pacing, sentence-boundary breaks, Persian text
  cleanup (Arabic yeh/kaf to Persian, half-spaces, punctuation).
- Three burn-in styles: cinema, vertical reels (9:16), bilingual
  learning.
- Per-job quality report listing the engine and model actually used.

### Known limits
- Offline Argos translation quality is serviceable, not great; the
  translator is pluggable by design.
- Live link downloads depend on the source site and the host network;
  some sites block datacenter IPs.
- The Persian model is heavy (about 6 GB in fp16) and needs a machine
  with enough free RAM or a GPU; a CT2 int8 conversion is picked up
  automatically when present.
