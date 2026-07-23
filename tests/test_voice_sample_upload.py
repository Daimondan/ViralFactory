"""Regression coverage for the live voice-reference upload path."""

import io
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VIRALFACTORY_DISABLE_BACKGROUND_WORKERS", "1")
    config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config"))
    app = create_app(config_dir=config_dir, db_path=str(tmp_path / "test.db"))
    app.config["TESTING"] = True
    monkeypatch.chdir(tmp_path)
    return app.test_client(), tmp_path


def test_upload_m4a_converts_to_reference_wav(client, tmp_path):
    source = tmp_path / "clean-reference.m4a"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
        capture_output=True,
    )

    with source.open("rb") as audio:
        response = client[0].post(
            "/api/voices/upload-sample",
            data={"file": (io.BytesIO(audio.read()), "clean-reference.m4a")},
            content_type="multipart/form-data",
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["filename"] == "clean-reference.wav"
    output = client[1] / payload["path"]
    assert output.is_file()

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels,codec_name",
            "-of",
            "default=noprint_wrappers=1",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "sample_rate=24000" in probe
    assert "channels=1" in probe
    assert "codec_name=pcm_s16le" in probe
