# Contributing to SubFa

Welcome. SubFa exists so ordinary people can subtitle the videos in
their daily life. Contributions that keep it simple are the most
valuable ones.

## The easiest contribution: a glossary

A glossary is one JSON file in the `glossaries/` folder. It maps a
term to the exact translation viewers expect:

```json
{ "goalkeeper": "دروازه‌بان", "offside": "آفساید" }
```

To add one:

1. Create `glossaries/<topic>.json` with term pairs.
2. Use the glossary request issue template if you want feedback first.
3. Open a pull request. That is the whole process: one file, no code.

Good first issues are labelled `good first issue`, and glossary
requests are a steady source of them.

## Add a language

- Target languages work through the translator interface in
  `subfa/translate.py`. Argos Translate covers many pairs already;
  check its package index for your pair.
- UI strings for the bot live in `bot/bot.py` and for the web page in
  `web/static/index.html` (the `T` dictionary). Add your language to
  both, or open an issue and ask for help wiring it up.

## Add a downloader or engine

Transcription, translation and downloading are interfaces
(`subfa/transcribe.py`, `subfa/translate.py`, `subfa/download.py`).
A new engine is one class plus tests that use the fake
implementations as a model. Tests must run offline: never make the
test suite download a model or a video.

## Development

```bash
pip install -e ".[dev,web,bot]"
pytest -q
```

All tests run offline with fake engines. If your change touches the
pipeline, add or update a test in `tests/`.

## Ground rules

- No tokens, keys or personal files in commits. Tokens come from
  environment variables only.
- Error messages are written for non-developers, in English and
  Persian where the surface shows them.
- Keep the three surfaces (CLI, bot, web) on the same pipeline. A
  feature that only works in one surface needs a reason.
