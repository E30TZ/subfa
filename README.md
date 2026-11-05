# SubFa

[![CI](https://github.com/E30TZ/subfa/actions/workflows/ci.yml/badge.svg)](https://github.com/E30TZ/subfa/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/github/license/E30TZ/subfa)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

**Send a file, or paste a video link, get Persian subtitles back.**

SubFa turns a video or audio file into subtitles on your own machine:
a subtitle file in the target language (Persian by default), a
bilingual subtitle file, a plain transcript, and, for videos, a copy
with the subtitles burned in. No account, no uploads to strangers,
no per minute fees.

Persian version of this page: [README.fa.md](README.fa.md)

Demo (from the real smoke test in `smoke/SMOKE.md`: a synthetic
English speech clip, transcribed locally by Whisper tiny, burned in):

![SubFa demo](assets/demo.gif)

## What it does

- **Three ways in:** a Telegram bot, a small web page, and a CLI.
- **Two kinds of input:** upload a media file, or paste a link to a
  video page (YouTube and every other site yt-dlp supports).
- **Captions fast path:** if the video page already publishes
  subtitles or captions in the source language, SubFa uses them and
  skips speech recognition entirely. If they are missing or unusable,
  it falls back to Whisper automatically. The result always tells
  you which path was taken.
- **Local transcription with language-aware engines.** Stock
  Whisper is weak on Persian (published word error rates of
  20 to 56 percent), so Persian audio is routed to a Whisper model
  fine-tuned for Persian (`nezamisafa/whisper-persian-v4`, the top
  Persian model on the PESTE benchmark). Other languages use
  faster-whisper with `large-v3-turbo` and anti-hallucination
  decoding. Routing is automatic; the full decision record is in
  [docs/ASR.md](docs/ASR.md).
- **Offline translation** with Argos Translate. After a one time
  model download, translation works with no network at all.
- **Glossaries** fix technical terms: one JSON file per topic, applied
  after translation. Starters included: general, programming, gaming.
- **Outputs:** `name.fa.srt`, `name.bilingual.srt`,
  `name.transcript.txt`, and `name.subbed.mp4` for videos.

## Quick start

You need Python 3.10+, ffmpeg, and the project dependencies:

```bash
pip install -e ".[bot,web,translate]"
cp .env.example .env
```

### CLI

```bash
subfa lecture.mp4 --target fa --burn -o out/
subfa https://www.youtube.com/watch?v=VIDEO_ID --target fa --burn
subfa talk.mp3 --url https://example.com/talk --translator none
subfa lesson.mkv --glossary programming --bilingual -o out/
```

Run `subfa --help` for every option.

### Telegram bot

```bash
BOT_TOKEN=your-token-from-botfather python -m bot.bot
```

Send the bot a video, an audio file, a document, or paste a video
link. Pick the subtitle language with the buttons, and the bot sends
the subtitle files back and deletes its working copies.

Note: the public Telegram Bot API caps bot downloads at 20 MB and
uploads at 50 MB. Run a local Bot API server if you need larger
files. SubFa reports the effective cap instead of failing quietly.

### Web page

```bash
uvicorn web.app:app --host 0.0.0.0 --port 8000
```

Open the page, drop a file or paste a link, and download the results
when the job is done. Job files are deleted automatically one hour
after a job finishes.

### Docker

```bash
docker compose up web     # the web page on port 8000
docker compose up bot     # needs BOT_TOKEN in .env
```

Build with `--build-arg BUNDLE_MODELS=1` to download the speech
models into the image at build time, so the container never
downloads anything at runtime.

## Running fully offline (Iran friendly)

Speech and translation models are the only downloads SubFa ever
needs, and they are fetched once:

```bash
subfa download-models
```

This stores the faster-whisper model, the Persian fine-tuned
model and (when Argos is the translator) the Argos en/fa packages
in one cache folder (`SUBFA_MODEL_CACHE`, default
`~/.cache/subfa/models`). After that:

- Copy the folder to any machine, or keep it on the server.
- Run with `HF_HUB_OFFLINE=1` and no network at all. Transcription
  and translation are 100 percent local.

Mirrors: the downloads go through Hugging Face tooling, which
respects the `HF_ENDPOINT` environment variable. If the main hub
is slow or unreachable from your network, set `HF_ENDPOINT` to a
mirror before running `download-models`. The Docker build accepts
models bundled at build time (`BUNDLE_MODELS=1`, see above), which
is the most reliable option for servers in Iran: build once where
the network works, ship the image.

## Video links and your responsibility

Link downloading is powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp).
Two honest limits apply, both configurable in `.env`:

- `SUBFA_MAX_DURATION_MIN` (default 60) and `SUBFA_MAX_DOWNLOAD_MB`
  (default 500). Downloads are also capped at 720p by default
  (`SUBFA_DOWNLOAD_MAX_HEIGHT`), because subtitling does not need 4K.
- Only download or subtitle content you have the right to use: your
  own uploads, public domain work, or material you have permission
  for. SubFa is a subtitling tool, not a way around anyone's rights.

## Privacy

Files are processed locally, in a temporary folder, and deleted when
the job ends. Downloads from links are deleted with the job too.
Nothing is sent to a cloud transcription or translation service:
speech recognition runs on your machine and Argos Translate works
offline. The burned-in video is the only output that leaves the machine, and
only because you send or download it yourself.

## Quality features

Subtitles are a reading experience, and this is where toy tools
fail. SubFa treats these as rules with tests, not hopes:

- **Cue craft:** at most 42 characters per line and 2 lines per cue,
  a reading speed target of at most 20 characters per second, breaks
  at sentence ends first and clause ends second, and cues shorter
  than one second are merged instead of flashing.
- **Persian text cleanup:** Arabic Yeh and Kaf are normalized to
  Persian, ZWNJ (نیم‌فاصله) is applied to common patterns
  (می‌شود، کتاب‌ها، بزرگ‌تر), punctuation spacing and Persian quotes
  are fixed, and digits are rendered consistently (config:
  `SUBFA_DIGITS=fa|en|keep`).
- **Translation with context:** cues are translated in sliding
  windows of 10 with 2 context cues on each side, so pronouns and
  split sentences stay coherent. Glossaries apply after translation.
- **Style presets for burn-in:** `cinema` (bottom, large, strong
  outline), `reels` (vertical 9:16 safe area, bold, raised), and
  `learning` (bilingual, source line smaller above the translation).
  Pick with `--style` in the CLI, buttons in the bot, or the web form.
- **Web subtitle editor:** after a web job, open the edit page from
  the result, fix cue text and timing, save, and re-burn or
  re-download without re-transcribing.
- **Quality report per job:** every job writes a `report.txt` (and
  the bot and web page show the summary): cue count, percent of cues
  over the reading speed limit, transcript path taken (published
  captions or Whisper, with the model), and glossary terms applied.
  All numbers are computed from the actual cues.

## Persian subtitle styling

Burned-in subtitles use ASS styling through libass with the
**Vazirmatn** font by default. libass applies the Unicode bidi
algorithm, so Persian lines render right to left correctly. Install
Vazirmatn for the intended look (the Docker image tries to install
`fonts-vazirmatn`); without it, libass falls back to a system font
and subtitles still work with a plainer look. Set another font with
`SUBFA_FONT`. The web page uses Vazirmatn when available, with
system font fallbacks, which is good enough for v0.1.

## Glossaries

A glossary is one JSON file in `glossaries/`, mapping a term to the
exact translation the community wants:

```json
{ "programming": "برنامه‌نویسی", "bug": "باگ" }
```

Adding or improving a glossary is the easiest contribution to
SubFa: one file, no code. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

- v0.1.0: file and link input, captions fast path, Persian and
  English subtitles, bilingual output, burn-in with style presets,
  glossaries, translation with context, web subtitle editor,
  quality report per job, bot, web page, CLI.
- Next: more target languages, speaker labels, a packaged desktop
  build, LLM based translation engines that use the context
  windows natively, and an experimental Parakeet engine
  (see docs/ASR.md for why it is not the default).

## License

MIT. See [LICENSE](LICENSE).
