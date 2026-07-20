import time
import wave
from pathlib import Path

from phone_agent.config import get_settings
from phone_agent.stt_benchmark import latest_real_call_id, real_call_wavs


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 800)


def test_latest_real_call_id_detects_new_recording_directories(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_BASE_DIR", str(tmp_path))
    get_settings.cache_clear()

    old_call = "100_0"
    new_call = "200_0"
    _write_wav(tmp_path / "recordings" / old_call / f"{old_call}-01.wav")
    time.sleep(0.01)
    _write_wav(tmp_path / "recordings" / new_call / f"{new_call}-01.wav")

    assert latest_real_call_id() == new_call


def test_real_call_wavs_ignores_agent_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_BASE_DIR", str(tmp_path))
    get_settings.cache_clear()

    call_id = "300_0"
    keep = tmp_path / "recordings" / call_id / f"{call_id}-01.wav"
    _write_wav(keep)
    for suffix in ("-reply.wav", "-min.wav", "-tail.wav", ".stt.wav"):
        _write_wav(tmp_path / "recordings" / call_id / f"{call_id}-01{suffix}")

    wavs = real_call_wavs(call_id)

    assert wavs == [keep.resolve()]
