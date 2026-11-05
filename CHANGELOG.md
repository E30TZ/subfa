# Changelog

All notable changes to SubFa are documented here.

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
