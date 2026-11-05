"""SubFa web app: one drag and drop page, no build step.

Run:
    uvicorn web.app:app --host 0.0.0.0 --port 8000

Upload a file or paste a video link, poll the job, download the
subtitle files. Job folders live in a temp directory and are wiped
one hour after the job finishes.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from subfa import SubfaError
from subfa.burn import burn_subtitles
from subfa.config import is_video, load_settings
from subfa.download import is_url, make_downloader
from subfa.messages import limit_message
from subfa.pipeline import QUALITY_HEIGHTS, Pipeline, normalize_quality, normalize_tone
from subfa.srt import Cue, cues_to_srt, parse_srt
from subfa.transcribe import make_engine
from subfa.translate import make_translator

settings = load_settings()
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="SubFa")
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
JOB_TTL_SECONDS = 3600


def decide_input(filename: str | None, url: str | None) -> tuple[str, str]:
    """Route a submission to ("file", name) or ("url", link).

    A pasted link wins only when no file was uploaded. Raises
    ValueError with a user facing message otherwise.
    """
    if filename:
        return "file", filename
    if url and is_url(url.strip()):
        return "url", url.strip()
    raise ValueError("Send a media file or a valid video link.")


def _set_job(job_id: str, **fields) -> None:
    with JOBS_LOCK:
        JOBS[job_id].update(fields)


def _cleanup_later(job_dir: Path) -> None:
    timer = threading.Timer(JOB_TTL_SECONDS, shutil.rmtree, args=[job_dir], kwargs={"ignore_errors": True})
    timer.daemon = True
    timer.start()


def _run_job(job_id: str, kind: str, value: str, saved_file: Path | None,
             target: str, glossary_names: list[str], burn: bool, bilingual: bool,
             style: str, quality: str, tone: str) -> None:
    job_dir = Path(JOBS[job_id]["dir"])

    def progress(stage: str, fraction: float, note: str) -> None:
        _set_job(job_id, stage=stage, fraction=fraction)

    pipeline = Pipeline(
        settings=settings,
        engine=make_engine(settings),
        translator=make_translator(settings),
        downloader=make_downloader(settings),
        progress=progress,
    )
    try:
        if kind == "file":
            _set_job(job_id, media_path=str(saved_file))
            result = pipeline.run_file(
                saved_file, job_dir / "out", target, "auto",
                glossary_names, burn, bilingual, style, quality, tone,
            )
        else:
            result = pipeline.run_url(
                value, job_dir / "out", job_dir / "download", target,
                "auto", glossary_names, burn, bilingual, style, quality, tone,
            )
            downloads = list((job_dir / "download").glob("*"))
            media = next(
                (p for p in downloads if p.suffix.lower() not in (".srt", ".vtt")),
                None,
            )
            if media is not None:
                _set_job(job_id, media_path=str(media))
        _set_job(
            job_id,
            status="done",
            stage="done",
            fraction=1.0,
            path_used=result.path_used,
            title=result.title,
            tone_resolved=result.tone_resolved,
            caption_track=result.caption_track,
            outputs={k: str(p) for k, p in result.outputs.items()},
            report=result.report.to_dict() if result.report else None,
        )
    except SubfaError as exc:
        code = str(exc)
        if code in ("too_long", "too_big", "too_large_upload"):
            en, fa = limit_message(code, settings)
            _set_job(job_id, status="error", error=f"{en} / {fa}")
        else:
            _set_job(job_id, status="error", error=code)
    except Exception as exc:  # keep the job record honest
        _set_job(job_id, status="error", error=f"Unexpected error: {exc}")
    finally:
        _cleanup_later(job_dir)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/config")
def config() -> dict:
    return {
        "max_file_mb": settings.max_file_mb,
        "max_duration_min": settings.max_duration_seconds // 60,
        "max_download_mb": settings.max_download_mb,
    }


@app.post("/jobs")
async def create_job(
    file: UploadFile | None = File(default=None),
    url: str = Form(default=""),
    target: str = Form(default="fa"),
    glossary: str = Form(default=""),
    burn: bool = Form(default=False),
    bilingual: bool = Form(default=False),
    style: str = Form(default="cinema"),
    quality: str = Form(default="720"),
    tone: str = Form(default="auto"),
):
    filename = file.filename if file and file.filename else None
    try:
        kind, value = decide_input(filename, url or None)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    job_id = uuid.uuid4().hex[:12]
    job_dir = Path(tempfile.mkdtemp(prefix=f"subfa-web-{job_id}-"))
    saved_file: Path | None = None
    if kind == "file":
        data = await file.read()
        if len(data) > settings.max_file_bytes:
            en, fa = limit_message("too_large_upload", settings)
            shutil.rmtree(job_dir, ignore_errors=True)
            return JSONResponse({"error": f"{en} / {fa}"}, status_code=413)
        saved_file = job_dir / (filename or "upload.bin")
        saved_file.write_bytes(data)

    if style not in ("cinema", "reels", "learning"):
        style = "cinema"
    quality = normalize_quality(quality)
    tone = normalize_tone(tone)
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running", "stage": "start", "fraction": 0.0,
            "dir": str(job_dir), "outputs": {}, "style": style,
            "quality": quality, "tone": tone, "tone_resolved": "",
            "caption_track": "",
            "media_path": None, "report": None,
        }
    glossary_names = [g.strip() for g in glossary.split(",") if g.strip()]
    thread = threading.Thread(
        target=_run_job,
        args=(job_id, kind, value, saved_file, target, glossary_names, burn, bilingual, style, quality, tone),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
def job_status(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return JSONResponse({"error": "Unknown job"}, status_code=404)
        return {
            "status": job["status"],
            "stage": job["stage"],
            "fraction": job["fraction"],
            "path_used": job.get("path_used"),
            "title": job.get("title", ""),
            "error": job.get("error"),
            "quality": job.get("quality", ""),
            "tone": job.get("tone", ""),
            "tone_resolved": job.get("tone_resolved", ""),
            "caption_track": job.get("caption_track", ""),
            "outputs": sorted(job.get("outputs", {}).keys()),
            "report": job.get("report"),
        }


@app.get("/jobs/{job_id}/files/{kind}")
def job_file(job_id: str, kind: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None or kind not in job.get("outputs", {}):
            return JSONResponse({"error": "Unknown file"}, status_code=404)
        path = Path(job["outputs"][kind])
    if not path.exists():
        return JSONResponse({"error": "File was cleaned up"}, status_code=410)
    return FileResponse(path, filename=path.name)


# -- Subtitle editor ---------------------------------------------------
# After a job finishes, the user can fix cue text in the browser and
# re-burn or re-download, without re-running transcription or
# translation. The editor works on the job's stored SRT file.


def _job_or_none(job_id: str) -> dict | None:
    with JOBS_LOCK:
        return JOBS.get(job_id)


@app.get("/jobs/{job_id}/edit", response_class=HTMLResponse)
def edit_page(job_id: str) -> str:
    return (STATIC_DIR / "edit.html").read_text(encoding="utf-8")


@app.get("/jobs/{job_id}/cues")
def get_cues(job_id: str, kind: str = "srt"):
    job = _job_or_none(job_id)
    if job is None or kind not in job.get("outputs", {}):
        return JSONResponse({"error": "Unknown job or subtitle kind"}, status_code=404)
    path = Path(job["outputs"][kind])
    if not path.exists():
        return JSONResponse({"error": "Subtitle file was cleaned up"}, status_code=410)
    cues = parse_srt(path.read_text(encoding="utf-8"))
    return {
        "kind": kind,
        "cues": [
            {"start": c.start, "end": c.end, "text": c.text} for c in cues
        ],
    }


@app.post("/jobs/{job_id}/cues")
async def save_cues(job_id: str, payload: dict, kind: str = "srt"):
    job = _job_or_none(job_id)
    if job is None or kind not in job.get("outputs", {}):
        return JSONResponse({"error": "Unknown job or subtitle kind"}, status_code=404)
    path = Path(job["outputs"][kind])
    try:
        cues = [
            Cue(float(c["start"]), float(c["end"]), str(c["text"]))
            for c in payload.get("cues", [])
        ]
    except (KeyError, TypeError, ValueError):
        return JSONResponse({"error": "Invalid cue data"}, status_code=400)
    if not cues:
        return JSONResponse({"error": "No cues given"}, status_code=400)
    path.write_text(cues_to_srt(cues), encoding="utf-8")
    return {"saved": len(cues), "kind": kind}


@app.post("/jobs/{job_id}/reburn")
def reburn(job_id: str, kind: str = "srt"):
    job = _job_or_none(job_id)
    if job is None:
        return JSONResponse({"error": "Unknown job"}, status_code=404)
    media_path = job.get("media_path")
    if not media_path or not Path(media_path).exists() or not is_video(media_path):
        return JSONResponse(
            {"error": "This job has no video to re-burn (audio job, or files cleaned up)."},
            status_code=400,
        )
    if kind not in job.get("outputs", {}):
        return JSONResponse({"error": "Unknown subtitle kind"}, status_code=404)
    srt_path = Path(job["outputs"][kind])
    cues = parse_srt(srt_path.read_text(encoding="utf-8"))
    out_dir = Path(job["dir"]) / "out"
    output_path = out_dir / (Path(media_path).stem + ".subbed.mp4")
    try:
        burn_subtitles(
            media_path,
            cues,
            output_path,
            font=settings.subtitle_font,
            work_dir=out_dir / "_work",
            style=job.get("style", "cinema"),
            max_height=QUALITY_HEIGHTS.get(job.get("quality", "720")),
        )
    except SubfaError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    _set_job(job_id, outputs={**job["outputs"], "burned": str(output_path)})
    return {"burned": output_path.name}
