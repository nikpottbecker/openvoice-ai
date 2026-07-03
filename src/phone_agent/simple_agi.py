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

    def stream_file(self, filename: str) -> str:
        return self.command(f'STREAM FILE "{filename}" ""')

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
