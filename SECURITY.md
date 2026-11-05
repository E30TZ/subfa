# Security Policy

## Reporting a vulnerability

If you find a security issue in SubFa, please report it privately
instead of opening a public issue:

- Open a private vulnerability report from the repository's
  **Security** tab ("Report a vulnerability"), or
- Contact the maintainer through their GitHub profile.

Please include the version or commit, steps to reproduce, and the
impact you observed. You should get a first reply within a few days.

## Scope notes

SubFa runs locally: media files, models and subtitles stay on the
user's own machine unless the user explicitly runs the Telegram bot
or the web app on a server. The bot reads its token only from the
`BOT_TOKEN` environment variable; never commit a token to this
repository. Downloaded models are loaded from the local model cache
(`SUBFA_MODEL_CACHE`) and can be used fully offline.
