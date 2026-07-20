import sys


class AGI:
    def __init__(self) -> None:
        self.env: dict[str, str] = {}
        while True:
            line = sys.stdin.readline().strip()
            if not line:
                break
            key, _, value = line.partition(":")
            self.env[key.strip()] = value.strip()

    def command(self, command: str) -> str:
        sys.stdout.write(command + "\n")
        sys.stdout.flush()
        return sys.stdin.readline().strip()

    def answer(self) -> str:
        return self.command("ANSWER")

    def hangup(self) -> str:
        return self.command("HANGUP")

    def stream_file(self, filename: str, escape_digits: str = "") -> str:
        return self.command(f'STREAM FILE "{filename}" "{escape_digits}"')

    def wait_for_digit(self, timeout_ms: int) -> str:
        return self.command(f"WAIT FOR DIGIT {timeout_ms}")

    def record_file(
        self,
        filename: str,
        format_: str,
        escape_digits: str,
        timeout_ms: int,
        offset_samples: int,
        beep: bool,
        silence_seconds: float,
    ) -> str:
        beep_flag = "beep" if beep else ""
        silence_arg = f" s={silence_seconds}" if silence_seconds and silence_seconds > 0 else ""
        return self.command(
            f'RECORD FILE "{filename}" {format_} "{escape_digits}" '
            f"{timeout_ms} {offset_samples} {beep_flag}{silence_arg}"
        )


def agi_digit(response: str) -> str:
    marker = "result="
    if marker not in response:
        return ""
    value = response.split(marker, 1)[1].split()[0].strip()
    if not value or value in {"0", "-1"}:
        return ""
    try:
        codepoint = int(value)
    except ValueError:
        return ""
    if 0 < codepoint < 128:
        return chr(codepoint)
    return ""
