"""Quality point 5: the web subtitle editor endpoints."""

import shutil
import subprocess

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from subfa.srt import Cue, cues_to_srt  # noqa: E402
from web import app as web_app  # noqa: E402


def _seed_job(tmp_path, with_video=False):
    job_id = "testjob123"
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True)
    srt_path = out_dir / "clip.fa.srt"
    original = cues_to_srt([Cue(0.0, 2.0, "سلام"), Cue(2.0, 4.0, "دنیا")])
    srt_path.write_text(original, encoding="utf-8")
    media_path = None
    if with_video:
        media_path = tmp_path / "clip.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
             "-shortest", str(media_path)],
            check=True, capture_output=True,
        )
    web_app.JOBS[job_id] = {
        "status": "done", "stage": "done", "fraction": 1.0,
        "dir": str(tmp_path), "outputs": {"srt": str(srt_path)},
        "style": "cinema",
        "media_path": str(media_path) if media_path else None,
        "report": None,
    }
    return job_id, srt_path


def test_pages_have_persistent_language_toggle():
    client = TestClient(web_app.app)
    index = client.get("/").text
    edit = client.get("/jobs/whatever/edit").text
    for page in (index, edit):
        assert 'id="langBtn"' in page
        assert "data-i18n" in page
        # Both pages share one localStorage key, so the language
        # chosen on the index page carries over to the editor.
        assert 'localStorage.getItem("subfa-lang")' in page
        assert 'localStorage.setItem("subfa-lang"' in page


def test_editor_get_cues(tmp_path):
    job_id, _ = _seed_job(tmp_path)
    client = TestClient(web_app.app)
    res = client.get(f"/jobs/{job_id}/cues")
    assert res.status_code == 200
    cues = res.json()["cues"]
    assert len(cues) == 2 and cues[0]["text"] == "سلام"


def test_editor_save_cues_rewrites_srt(tmp_path):
    job_id, srt_path = _seed_job(tmp_path)
    client = TestClient(web_app.app)
    res = client.post(
        f"/jobs/{job_id}/cues",
        json={"cues": [
            {"start": 0.0, "end": 2.0, "text": "سلام اصلاح‌شده"},
            {"start": 2.0, "end": 4.0, "text": "دنیا"},
        ]},
    )
    assert res.status_code == 200
    assert res.json()["saved"] == 2
    saved_text = srt_path.read_text(encoding="utf-8")
    assert "سلام اصلاح‌شده" in saved_text
    # And the editor reads back the fixed text.
    cues = client.get(f"/jobs/{job_id}/cues").json()["cues"]
    assert cues[0]["text"] == "سلام اصلاح‌شده"


def test_editor_rejects_unknown_job(tmp_path):
    client = TestClient(web_app.app)
    assert client.get("/jobs/nope/cues").status_code == 404
    assert client.post("/jobs/nope/cues", json={"cues": []}).status_code == 404


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_editor_reburn_uses_edited_text(tmp_path):
    job_id, _ = _seed_job(tmp_path, with_video=True)
    client = TestClient(web_app.app)
    client.post(
        f"/jobs/{job_id}/cues",
        json={"cues": [{"start": 0.0, "end": 0.9, "text": "Edited cue"}]},
    )
    res = client.post(f"/jobs/{job_id}/reburn")
    assert res.status_code == 200
    burned = web_app.JOBS[job_id]["outputs"]["burned"]
    from pathlib import Path

    assert Path(burned).exists() and Path(burned).stat().st_size > 0
