from scripts.analyze_call_timings import build_summary, parse_log


def test_analyze_call_timings_extracts_turn_totals(tmp_path) -> None:
    log_path = tmp_path / "phone-agent.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-07-09 INFO timing call_id=call1 turn=1 phase=record seconds=2.000 min_record=1.2 silence=1.3 size=1234",
                "2026-07-09 INFO timing call_id=call1 turn=1 phase=recording_audio duration=1.900",
                "2026-07-09 INFO timing call_id=call1 turn=1 phase=stt seconds=0.800",
                "2026-07-09 INFO timing call_id=call1 turn=1 phase=stt_detail recording_duration=1.900 preprocessing=0.100 whisper=0.700 model=base avg_logprob=-0.2 no_speech_prob=0.1 compression_ratio=1.0 segments=1 retry_model= retry_whisper=",
                "2026-07-09 INFO transcript_full call_id=call1 turn=1 text=Ich moechte einen Termin",
                "2026-07-09 INFO timing call_id=call1 turn=1 phase=llm seconds=0.400",
                "2026-07-09 INFO timing call_id=call1 turn=1 phase=tts seconds=0.500 size=4321",
                "2026-07-09 INFO timing call_id=call1 turn=1 phase=playback seconds=1.000",
                "2026-07-09 INFO timing call_id=call1 turn=1 phase=dtmf_wait seconds=0.250 timeout_ms=250",
                "2026-07-09 INFO audio_quality call_id=call1 turn=1 path=/tmp/call1-01.wav sample_rate=8000 channels=1 duration=1.900 rms_dbfs=-42.0 peak_dbfs=-12.0 clipping_percent=0.0000 flags=very_low_level",
                "2026-07-09 INFO dtmf_detected call_id=call1 turn=1 digit=1 source=pre_record",
            ]
        ),
        encoding="utf-8",
    )

    calls = parse_log(log_path)
    summary = build_summary("call1", calls["call1"])

    assert summary["avg_stt"] == 0.8
    assert summary["avg_dtmf_wait"] == 0.25
    assert summary["dtmf_count"] == 1
    assert summary["dtmf_events"][0]["source"] == "pre_record"
    assert summary["audio_quality_flags"] == ["very_low_level"]
    assert summary["diagnosis"] == ["recording_too_quiet_check_gain_or_normalization"]
    assert summary["avg_after_record_total"] == 2.7
    assert summary["turns"][0]["whisper"] == 0.7
    assert summary["turns"][0]["audio_quality"]["rms_dbfs"] == -42.0
    assert summary["turns"][0]["transcript"] == "Ich moechte einen Termin"
