# ASR engine decision record

Which speech recognition models SubFa runs, why, and what the
published numbers actually say. Decision made 2026-11-05.

The short version: **stock Whisper is weak on Persian, so SubFa
does not use it for Persian.** Persian audio is routed to a Whisper
model that was fine-tuned for Persian. Everything else uses
faster-whisper with a strong general model and anti-hallucination
decoding. All of it runs locally; see "Running fully offline" in
the README for model delivery.

## خلاصه فارسی

ویس فارسی با ویسپر معمولی خوب پیاده نمی‌شود (خطای کلمه‌ای حدود
۲۰ تا ۵۶ درصد، بسته به اندازه مدل). برای همین SubFa صدای فارسی را
به یک مدل ویسپر که مخصوص فارسی فاین‌تیون شده می‌فرستد
(nezamisafa/whisper-persian-v4، بهترین مدل فارسی در بنچمارک
PESTE با خطای کلمه‌ای ۱۳٫۱۸ درصد). بقیه زبان‌ها با faster-whisper
و مدل large-v3-turbo پیاده می‌شوند. همه‌چیز لوکال اجرا می‌شود و
مدل‌ها با دستور `subfa download-models` یک بار دانلود و بعد کاملا
آفلاین استفاده می‌شوند. جزئیات و منابع در ادامه آمده است.

## The problem with stock Whisper on Persian

An experienced user warned us that "Whisper fails". For Persian,
the published benchmarks back that warning for stock models:

| Model | Benchmark | WER | CER | Source |
|---|---|---|---|---|
| nezamisafa/whisper-persian-v4 (fine-tuned large-v3) | PESTE, FLEURS fa (871 clips) | **13.18%** | **4.97%** | PESTE leaderboard, #1 |
| vhdm/whisper-large-fa-v1 (fine-tuned) | PESTE, FLEURS fa | 14.57% | not listed here | PESTE leaderboard, #2 |
| Stock whisper-large-v3 | PESTE, FLEURS fa | 20.37% | not listed here | PESTE leaderboard |
| Stock whisper-medium | FLEURS fa | about 41% | not listed here | Interspeech 2026 Persian ASR paper |
| Stock whisper-small | FLEURS fa | about 55.8% | not listed here | Interspeech 2026 Persian ASR paper |
| nezamisafa/whisper-persian-v4 (author's own eval) | author's test set | 8.73% | not listed here | model card |

All numbers above are external, published results, not SubFa
measurements. SubFa's own harness is `tools/benchmark_asr.py`;
local run results, when they exist, live in `smoke/ASR-BENCH.md`
and say exactly what ran.

## The routing SubFa ships

`SUBFA_ASR_ENGINE=auto` (default):

- Source language Persian (given, or detected): the Persian
  fine-tuned engine. Default model
  `nezamisafa/whisper-persian-v4`, top of the PESTE leaderboard.
  Backend: the Hugging Face transformers pipeline, because no
  official CTranslate2 conversion of this model is published
  (checked on the Hub, 2026-11-05). If a folder containing a
  CTranslate2 conversion (`model.bin`) is configured instead, the
  engine runs it through faster-whisper automatically.
- Any other language: faster-whisper, default model
  `large-v3-turbo`, with anti-hallucination decoding on.

`SUBFA_ASR_ENGINE=persian` or `=whisper` forces one engine.
Every job's `report.txt` states the engine and model that
actually ran.

## Anti-hallucination decoding

Whisper is known to invent text on silence, music and noise.
The standard mitigation, on by default here and configurable in
`.env`, is:

- `vad_filter=True`: voice activity detection trims non-speech.
- `no_speech_threshold=0.6`: segments likely to be silence are
  skipped instead of transcribed.
- `log_prob_threshold=-1.0` and `compression_ratio_threshold=2.4`:
  low-confidence or degenerate (looping) decodes are rejected.
- `condition_on_previous_text=False`: an early hallucination
  cannot cascade through the rest of the file.
- `beam_size=5`: a modest beam for accuracy over speed.

## Alternatives evaluated and not chosen as default

**NVIDIA Parakeet-TDT-0.6b-v3.** Fast and strong on its published
languages, and Persian is in its 25-language list. Not chosen:
no published Persian WER exists for it, its language auto-detect
is documented to misfire on some languages, and it pulls in the
heavy NeMo stack, which is a poor fit for a tool aimed at ordinary
machines. Kept as a future experimental engine candidate.

**Meta SeamlessM4T-v2.** One model for speech recognition,
translation and more, with Persian support. Not chosen as a
default: it is released under CC-BY-NC 4.0 (non-commercial),
which conflicts with this project's MIT, commercial-friendly
stance, and at about 2.3B parameters it is heavy for CPU-only
machines. It may return later as an optional plugin with a clear
license warning.

**Stock faster-whisper for everything (the old v0.1.0 design).**
Simple, but the Persian numbers in the table above are exactly
the failure the owner was warned about. Kept for non-Persian
audio and as a forced option.

## Sources

- PESTE Persian ASR benchmark and leaderboard:
  https://github.com/ArmanJR/PESTE-Benchmark
- Persian fine-tuned model (model card with the author's own
  evaluation): https://huggingface.co/nezamisafa/whisper-persian-v4
- Persian ASR results for stock Whisper model sizes, Interspeech
  2026 paper (ISCA Archive):
  https://www.isca-archive.org/interspeech_2026/ (Persian ASR paper)
