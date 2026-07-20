from scripts.benchmark_conversation_flows import SCENARIOS, run_scenario


def test_all_benchmark_scenarios_complete() -> None:
    rows = [run_scenario(scenario) for scenario in SCENARIOS]

    assert all(row["completed"] for row in rows)
    assert all(row["expected_slot"] is None for row in rows)


def test_compressed_hybrid_appointment_uses_fewer_inputs_than_dtmf_flow() -> None:
    rows = {scenario.name: run_scenario(scenario) for scenario in SCENARIOS}

    assert rows["dtmf_appointment_full"]["inputs"] == 5
    assert rows["hybrid_appointment_compressed"]["inputs"] == 3
    assert rows["hybrid_appointment_compressed"]["inputs"] < rows["dtmf_appointment_full"]["inputs"]


def test_short_flows_stay_short() -> None:
    rows = {scenario.name: run_scenario(scenario) for scenario in SCENARIOS}

    assert rows["callback_confirm"]["inputs"] == 2
    assert rows["message"]["inputs"] == 2
    assert rows["callback_confirm"]["reply_chars"] < 120
