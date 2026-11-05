# ASR benchmark results (local runs)

Everything in the "Ran" sections was actually executed in this
environment on 2026-11-05 with `tools/benchmark_asr.py` and the
in-repo WER/CER implementation (`subfa/metrics.py`). Numbers from
external publications live in `docs/ASR.md` and are labelled as
external there; nothing external is copied into the result tables
below.

## Environment

- Python 3.12.3, faster-whisper 1.2.1, ctranslate2 4.8.5,
  transformers 5.22.1, torch 2.15.0 (CPU only, 4 cores)
- Host RAM 8 GB total, shared with other services on this box:
  about 0.9 to 2.3 GB free during these runs (measured with
  `free -m` before and after). This matters below.
- Models were placed in `.model-cache/` (gitignored) in the exact
  layout `subfa download-models` produces. Because the canonical
  Systran repo answered HTTP 401 through this network's egress
  proxy at first attempt, the large-v3-turbo CTranslate2 weights
  came from the mirror repo `deepdml/faster-whisper-large-v3-turbo-ct2`
  (revision 4df90f75321148c3a29a9e2351b7ddf8f5b115a8); the file size
  matches the official X-Linked-Size exactly (1,617,884,929
  bytes). The small model came from `Systran/faster-whisper-small`
  (model.bin 483,546,902 bytes, exact official size).

## Test clips

English (in the repo manifest, `tools/benchmark_manifest.json`):
- `tools/benchmark_data/en_speech.wav`, 4.61 s, synthetic speech
  from ffmpeg's flite filter (voice slt). Reference: "Hello world.
  Programming is fun. Subtitles help everyone learn faster."

Persian (local manifest `smoke/bench/manifest.json`, audio kept
out of git): the first 3 clips of the FLEURS fa_ir test split
(Google FLEURS, CC-BY-4.0, https://huggingface.co/datasets/google/fleurs),
downloaded as the official parquet (844,186,933 bytes, size
verified), converted to 16 kHz mono wav:
- `fleurs_fa_0.wav`, 16.98 s, reference begins
  «این سند بر اساس این درز اطلاعاتی است و به اختلاف مرزی مربوط می‌شود...»
- `fleurs_fa_1.wav`, 11.22 s, reference begins
  «این کمیسیون پاسخ مارتلی بود به اعتراضات گسترده ضدحکومتی...»
- `fleurs_fa_2.wav`, 13.80 s, reference begins
  «زمانی که از همه منابع موجود به شکلی مؤثر در واحدهای عملیاتی سازمانی استفاده شود...»

Full reference texts are in `smoke/bench/manifest.json`.

## Ran: English, new default engine (large-v3-turbo)

Command: `tools/benchmark_asr.py --engine whisper` with default
settings (faster-whisper, large-v3-turbo, CTranslate2 int8,
anti-hallucination decoding on: VAD filter, no_speech_threshold
0.6, log_prob_threshold -1.0, compression_ratio_threshold 2.4,
condition_on_previous_text off, beam_size 5).

| Clip | Engine | WER | CER | Time |
|---|---|---|---|---|
| en_speech.wav | faster-whisper / large-v3-turbo | 0.000 | 0.000 | 42.4 s (including model load) |

Hypothesis matched the reference exactly: "Hello world,
programming is fun. Subtitles help everyone learn faster."

## Ran: Persian, stock whisper-small (the old design's class of model)

Command: `SUBFA_WHISPER_MODEL=small tools/benchmark_asr.py
--manifest smoke/bench/manifest.json --engine whisper`
(stock faster-whisper small, CTranslate2 int8, same
anti-hallucination decoding, language forced to fa).

| Clip | Engine | WER | CER | Time |
|---|---|---|---|---|
| fleurs_fa_0.wav | faster-whisper / small | 0.607 | 0.224 | 10.0 s |
| fleurs_fa_1.wav | faster-whisper / small | 0.533 | 0.177 | 5.5 s |
| fleurs_fa_2.wav | faster-whisper / small | 0.619 | 0.143 | 6.5 s |
| mean | | **0.586** | **0.181** | |

The hypotheses are visibly garbled Persian (for example clip 0
came back as «این سندت بر اصلاس این درز اتلاتی هست...»). The mean
WER of 0.586 on 3 clips sits right next to the published
Interspeech figure for stock small on FLEURS fa (55.8% WER over
the full split), which cross-checks both the harness and the
owner's warning: stock Whisper really does fail Persian.

## Persian fine-tuned model (nezamisafa/whisper-persian-v4)

Model revision: b84fc89f5d8c6a08acbd0930c74010f8bb555253 (Hub main
at download time). The snapshot was downloaded into
`.model-cache/persian/whisper-persian-v4` in exactly the layout
`subfa download-models` produces, and verified:

- `model-00001-of-00002.safetensors`: 4,993,448,880 bytes, exact
  official size.
- `model-00002-of-00002.safetensors`: 1,180,663,192 bytes, exact
  official size.
- All 1,259 tensors readable through the safetensors index
  (total 6,173,962,240 bytes of weights, float16).
- `AutoConfig`, `AutoTokenizer` (WhisperTokenizer, vocab 51,866)
  and `AutoFeatureExtractor` all load from the local folder with
  the network uninvolved.

Engine resolution was verified live: with the cache in place,
`PersianFineTunedEngine` finds the snapshot, and
`resolve_backend()` returns "transformers" (the snapshot has no
CTranslate2 `model.bin`, as expected).

**Full transcription on this host: BLOCKED by RAM, not by code.**
One real attempt was made on `fleurs_fa_1.wav` (11.22 s) through
the shipped engine, under a 4 GB virtual memory cap set to
protect the other services sharing this box. Weight loading
failed after 15.9 s with `MemoryError: Cannot allocate memory`.
The arithmetic is the whole story: the float16 weights alone are
6.17 GB, and this host had 2.0 to 2.45 GB of RAM available during
the attempt (8 GB total, the rest held by unrelated services).
No Persian WER/CER from this model is reported here, because none
was measured here. The published PESTE numbers for this model
(WER 13.18%, CER 4.97% on the full FLEURS fa split) are in
`docs/ASR.md`, labelled as external.

What unblocks it, in order of preference:
1. A machine with about 8 GB of free RAM (or any GPU with 8 GB):
   the same command, `tools/benchmark_asr.py --manifest
   smoke/bench/manifest.json --engine persian`, runs as shipped.
2. A CTranslate2 int8 conversion of the model (about 1.6 GB in
   RAM): proven feasible on this very host by the large-v3-turbo
   int8 run above, and the Persian engine already prefers a CT2
   folder automatically when one is configured. Producing the
   conversion itself needs a one-off machine with enough RAM to
   load the float16 weights once.

## Also verified along the way

- `subfa download-models` was exercised for real against this
  cache layout; the bulk transfers above were finished with
  resumable curl into the same folders after the long-running
  download session was stopped by the sandbox, and every file's
  final size was checked against the Hub's published size.
- The FLEURS parquet (844,186,933 bytes) was deleted after the
  three clips were extracted; the clips and manifest stay in
  `smoke/bench/` (gitignored) for the rerun on a bigger machine.
