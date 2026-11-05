# Smoke test report

Everything below was actually run in this environment on 2026-11-05.
Anything not listed as run is unverified, and it says so.

## Environment

- Python 3.12.3, ffmpeg 8.1.2
- faster-whisper 1.2.1, ctranslate2 4.8.5, **av 12.3.0 (pinned, see bug below)**
- yt-dlp 2026.10.26, argostranslate 1.11.0
- python-telegram-bot 22.8, fastapi 0.162.0
- Vazirmatn font installed on this machine (used by the burn-in check)

## Test media (synthetic, generated here)

No system TTS (espeak, festival, flite binary) exists in this
environment. ffmpeg's built-in **flite** filter does, so the speech
clip was synthesized with it:

- Text: "Hello world. Programming is fun. Subtitles help everyone learn faster."
- `flite=textfile=..., voice=slt` -> speech.wav (about 4.6 s)
- speech.wav + a plain dark green 640x360 video -> sample.mp4

## What ran for real

### 1. Whisper transcription (faster-whisper, tiny model) - PASS

`subfa sample.mp4 --target en --model tiny --translator none --burn`

- Wall time about 7 s including burn-in.
- Output SRT (kept as `smoke/sample.en.srt`) text:
  "Hello world, programming is fun, subtitles help everyone learn faster."
  This matches the spoken text (Whisper normalized punctuation and
  the three sentences arrived as one segment; segmentation produced
  1 cue, 0.0 s to 4.5 s, wrapped on 2 lines).

### 2. Bug found and fixed by this smoke test

The first run crashed inside faster-whisper: the environment had
PyAV 19 installed, and faster-whisper 1.2 calls PyAV with a keyword
that was removed in av 13+. Fix shipped in the repo: `av>=11,<13` is
pinned in `pyproject.toml` and `requirements/core.txt`, with a
comment explaining why.

### 3. Argos Translate EN to FA (real offline translation) - PASS

Install notes, honestly: the first `pip install argostranslate`
failed with "No space left on device" because this VM's /tmp is a
512 MB tmpfs and the torch stack does not fit. Retried with TMPDIR
on the real disk; the install then took about 19 minutes (large
torch download over a slow egress). The en to fa Argos package was
auto-downloaded on first use by the project's ArgosTranslator.

`subfa sample.mp4 --target fa --model tiny --translator argos --glossary programming --burn`

- First run 62 s total, second run (everything cached) 27 s.
- Real Persian output (kept as `smoke/sample.fa.srt`):

```srt
1
00:00:00,000 --> 00:00:04,500
Hello World، برنامه‌نویسی سرگرم کننده است.
زیرنویس‌ها به همه کمک می‌کنند سریعتر یاد بگیرند.
```

- The Persian cleanup is visible in real output: ZWNJ in
  زیرنویس‌ها, می‌کنند and برنامه‌نویسی (the last one via the
  known-compounds rule added after this run, covered by a unit test,
  then the run was repeated to confirm).
- Bilingual SRT produced with the same cues (`smoke/sample.bilingual.srt`).
- Quality report produced (`smoke/sample.report.txt`).
- Glossary terms applied: **0**, reported as 0. Reason: Argos output
  is already Persian, so the Latin glossary terms have nothing to
  match. The report counts replacements truthfully instead of
  guessing.

### 4. Burn-in rendering - PASS, measured

Subtitle area brightness (ffmpeg signalstats, bottom quarter of a
frame at 2 s): original video YMAX 66 (plain dark green), English
burned video YMAX 197, Persian burned video YMAX 210. The subtitle
glyphs are really rendered, for Persian with Vazirmatn available.
`assets/demo.gif` is cut from the real English burned output.

### 5. Web app live smoke - PASS

uvicorn was started with `SUBFA_MODEL=tiny SUBFA_TRANSLATOR=none`,
the sample was uploaded through the real HTTP API:

- POST /jobs -> job done, path_used "whisper", outputs:
  burned, report, srt, transcript; report JSON had the real cue
  count (1) and model name (faster-whisper / tiny).
- Editor: GET /jobs/{id}/cues returned the cue, POST save rewrote the
  text, POST /jobs/{id}/reburn produced a new subtitled video.

### 6. Telegram bot - NOT run live (by design)

No token was used anywhere in this build. The bot module imports
cleanly, its message routing is unit tested, and running it without
BOT_TOKEN exits with a clear "BOT_TOKEN environment variable is not
set." message (verified). A live bot run waits for the owner's
Gate 1 approval and the owner's own token.

### 7. yt-dlp live download - BLOCKED in this sandbox, not faked

Downloading a tiny public YouTube video ("Me at the zoo",
jNQXAC9IVRw, 19 s) through the shipped YtDlpDownloader failed here
for two environment reasons, in order:

1. TLS: yt-dlp verifies with its bundled certifi store, which does
   not include this VM's egress proxy CA, so verification fails
   (CERTIFICATE_VERIFY_FAILED) before any download.
2. With verification relaxed in the throwaway test harness only
   (never in shipped code), YouTube itself answered "Sign in to
   confirm you're not a bot" for this datacenter IP.

So the live link path is **unverified from this machine**. The
downloader is covered by offline tests (FakeDownloader: limits,
captions parsing, fast path selection, Whisper fallback). On a
normal home machine neither sandbox issue applies, but that claim
itself is untested here and is stated as such.

## Tests

`pytest` - **72 passed**, fully offline (fake engines, fixtures
generated with ffmpeg): SRT round trips, segmentation quality rules,
Persian cleanup examples, context window assembly, style presets,
quality report math, glossary, download routing and limits,
captions fast path and fallback, pipeline end to end, web editor
endpoints, bot and web routing.

## Kept samples (small files only)

- `smoke/sample.en.srt`, `smoke/sample.fa.srt`,
  `smoke/sample.bilingual.srt`, `smoke/sample.report.txt`
- `assets/demo.gif` (from the real burned sample)
- Media and work files from the runs were deleted; regenerate them
  with the commands above.

## Link download (yt-dlp TLS fix, 2026-11-05)

On this host every yt-dlp request died with
`CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate
chain`: egress goes through a TLS-intercepting proxy whose CA
bundle the environment names in `SSL_CERT_FILE` (and
`REQUESTS_CA_BUNDLE`), but yt-dlp defaults to certifi and ignores
it. Fix in `subfa/download.py`: when either variable is set, the
downloader passes yt-dlp's `no-certifi` compat opt, which makes it
load the system trust store (which honours `SSL_CERT_FILE`).
Certificate verification stays ON; nothing is disabled. An offline
test locks the option building.

Verified live through `YtDlpDownloader` itself, after the fix:

- YouTube, https://www.youtube.com/watch?v=z8UPAVTh2aE : TLS now
  passes; YouTube answers "Sign in to confirm you're not a bot"
  (datacenter IP wall). Not defeated, by design: no cookie hacks.
  YouTube links from this host stay blocked.
- archive.org, https://archive.org/details/BigBuckBunny_124 :
  PASS end to end. Downloaded "Big Buck Bunny" (source.avi,
  332,243,668 bytes) through the pipeline downloader. (A first
  attempt died on a transient proxy disconnect; the retry worked.)
- Vimeo, https://vimeo.com/76979871 : TLS passes and the extractor
  answers, but Vimeo now requires a logged-in account. Blocked by
  the site, not by TLS.
- Dailymotion: one sampled video was deleted ("Not found"); another
  requires browser impersonation (curl_cffi), which is not
  installed. Not verified end to end.
