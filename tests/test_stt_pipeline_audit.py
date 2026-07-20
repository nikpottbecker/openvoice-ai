import json
import wave
from array import array

from scripts.stt_pipeline_audit import audio_metrics, character_error_rate, word_error_rate, write_reference_template


def test_word_error_rate_exact_match() -> None:
    assert word_error_rate("Ich moechte einen Termin", "Ich moechte einen Termin") == 0.0


def test_word_error_rate_counts_substitution() -> None:
    assert word_error_rate("Ich moechte einen Termin", "Ich brauche einen Termin") == 0.25


def test_character_error_rate_normalizes_german_mojibake() -> None:
    assert character_error_rate("uebermorgen fuenfzehn", "Ã¼bermorgen fÃ¼nfzehn") == 0.0


def test_write_reference_template_for_call_wavs(tmp_path) -> None:
    app_dir = tmp_path / "app"
    call_id = "123_0"
    call_dir = app_dir / "recordings" / call_id
    call_dir.mkdir(parents=True)
    wav_path = call_dir / f"{call_id}-01.wav"
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 800)

    output = tmp_path / "references.json"
    write_reference_template(app_dir, [call_id], output)

    references = json.loads(output.read_text(encoding="utf-8"))
    metadata = json.loads(output.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    assert references == {wav_path.name: ""}
    assert metadata["calls"][call_id][0]["audio"]["sample_rate"] == 8000


def test_audio_metrics_detects_pcm_level_and_clipping(tmp_path) -> None:
    wav_path = tmp_path / "clipped.wav"
    samples = array("h", [0, 32767, -32768, 12000, -12000] * 2000)
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(samples.tobytes())

    metrics = audio_metrics(wav_path)

    assert metrics["pcm_peak_sample"] == 32768
    assert metrics["pcm_peak_dbfs"] == 0.0
    assert metrics["pcm_clipping_percent"] > 0
    assert "possible_clipping" in metrics["quality_flags"]


def test_audio_metrics_flags_digital_silence_and_short_audio(tmp_path) -> None:
    wav_path = tmp_path / "silence.wav"
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 400)

    metrics = audio_metrics(wav_path)

    assert metrics["pcm_rms_dbfs"] is None
    assert "digital_silence" in metrics["quality_flags"]
    assert "very_short_audio" in metrics["quality_flags"]
