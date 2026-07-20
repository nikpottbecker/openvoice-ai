from pathlib import Path

from phone_agent.config import get_settings
from phone_agent.tts import synthesize_with_config
from phone_agent.tts_config import TTSConfig


def test_synthesize_with_config_passes_voice_controls(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("PIPER_BIN", "/bin/piper")
    get_settings.cache_clear()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "--output_file" in command:
            output = Path(command[command.index("--output_file") + 1])
            output.write_bytes(b"RIFFxxxxWAVE")
        else:
            Path(command[-1]).write_bytes(b"RIFFxxxxWAVE")

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("phone_agent.tts.subprocess.run", fake_run)
    output = tmp_path / "out.wav"

    synthesize_with_config(
        "Hallo",
        output,
        TTSConfig(
            voice="de_DE-thorsten-high",
            fallback_voice="de_DE-thorsten-medium",
            length_scale=1.08,
            noise_scale=0.5,
            noise_w_scale=0.7,
            sentence_silence=0.3,
            volume=0.95,
        ),
    )

    piper_command = calls[0]
    assert "--length-scale" in piper_command
    assert piper_command[piper_command.index("--length-scale") + 1] == "1.08"
    assert piper_command[piper_command.index("--sentence-silence") + 1] == "0.3"
    assert piper_command[piper_command.index("--volume") + 1] == "0.95"
    assert "de_DE-thorsten-high.onnx" in piper_command[piper_command.index("--model") + 1]
    assert output.exists()


def test_synthesize_cache_key_includes_voice(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_BASE_DIR", str(tmp_path))
    get_settings.cache_clear()
    run_count = 0

    def fake_run(command, **kwargs):
        nonlocal run_count
        run_count += 1
        if "--output_file" in command:
            Path(command[command.index("--output_file") + 1]).write_bytes(b"RIFFxxxxWAVE")
        else:
            Path(command[-1]).write_bytes(b"RIFFxxxxWAVE")

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("phone_agent.tts.subprocess.run", fake_run)

    synthesize_with_config("Hallo", tmp_path / "one.wav", TTSConfig(voice="de_DE-thorsten-medium"))
    synthesize_with_config("Hallo", tmp_path / "two.wav", TTSConfig(voice="de_DE-thorsten-high"))

    assert run_count == 4
