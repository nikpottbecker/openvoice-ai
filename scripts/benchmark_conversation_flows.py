#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Callable

from phone_agent.menu import HybridMenuSession
from phone_agent.models import AgentState, LLMResult


@dataclass(frozen=True)
class Step:
    channel: str
    value: str


@dataclass(frozen=True)
class Scenario:
    name: str
    caller_id: str
    steps: tuple[Step, ...]


SCENARIOS = (
    Scenario(
        name="dtmf_appointment_full",
        caller_id="015735703185",
        steps=(Step("dtmf", "1"), Step("dtmf", "3"), Step("dtmf", "2"), Step("speech", "Fotoshooting"), Step("dtmf", "1")),
    ),
    Scenario(
        name="hybrid_appointment_compressed",
        caller_id="015735703185",
        steps=(Step("dtmf", "1"), Step("speech", "Freitag vormittags Fotoshooting"), Step("speech", "ja")),
    ),
    Scenario(
        name="callback_confirm",
        caller_id="015735703185",
        steps=(Step("dtmf", "4"), Step("speech", "klar")),
    ),
    Scenario(
        name="message",
        caller_id="anonymous",
        steps=(Step("dtmf", "5"), Step("speech", "Bitte wegen dem Event morgen zurueckrufen.")),
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows = [run_scenario(scenario) for scenario in SCENARIOS]
    report = {
        "scenario_count": len(rows),
        "avg_inputs": round(sum(row["inputs"] for row in rows) / len(rows), 3),
        "max_inputs": max(row["inputs"] for row in rows),
        "all_completed": all(row["completed"] for row in rows),
        "scenarios": rows,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
    return 0 if report["all_completed"] else 1


def run_scenario(scenario: Scenario) -> dict:
    state = AgentState(call_id=scenario.name, caller_id=scenario.caller_id)
    menu = HybridMenuSession(state)
    replies: list[str] = []
    results: list[LLMResult] = []

    handlers: dict[str, Callable[[str], LLMResult | None]] = {
        "dtmf": lambda value: menu.handle_slot_dtmf(value) or menu.handle_dtmf(value),
        "speech": menu.handle_speech_action,
    }
    for step in scenario.steps:
        result = handlers[step.channel](step.value)
        if result is None:
            replies.append("NO_MATCH")
            break
        results.append(result)
        replies.append(result.reply)
        if result.should_end_call:
            break

    return {
        "name": scenario.name,
        "inputs": len(results),
        "completed": bool(results and results[-1].should_end_call),
        "expected_slot": state.expected_slot,
        "menu_level": menu.menu_level,
        "intent": state.intent,
        "reply_chars": sum(len(reply) for reply in replies),
        "last_reply": replies[-1] if replies else "",
    }


def print_human(report: dict) -> None:
    print(
        "scenario_count={scenario_count} avg_inputs={avg_inputs} max_inputs={max_inputs} all_completed={all_completed}".format(
            **report
        )
    )
    for row in report["scenarios"]:
        print(
            "scenario={name} inputs={inputs} completed={completed} slot={expected_slot} "
            "level={menu_level} reply_chars={reply_chars}".format(**row)
        )


if __name__ == "__main__":
    raise SystemExit(main())
