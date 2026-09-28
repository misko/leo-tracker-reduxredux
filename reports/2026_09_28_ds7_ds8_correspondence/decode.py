"""Run the qualified DS7 numerical decoder unchanged on selected DS8 excerpts."""

import json
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[2]
    out = Path(__file__).parent / "local"
    tools = root / "reports/2026_09_27_ds7_header"
    for folder in sorted([*out.glob("ds8-*"), *out.glob("repeat-*")]):
        folder = folder.resolve()
        if not (folder / "labels.json").exists():
            continue
        if not (folder / "recovery.json").exists():
            with (folder / "recovery.log").open("w") as log:
                subprocess.run(
                    [sys.executable, str(tools / "recover.py"), "--out", str(folder)],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                    timeout=60,
                )
        if not (folder / "tcodes.json").exists():
            with (folder / "tcodes.log").open("w") as log:
                subprocess.run(
                    [
                        sys.executable,
                        str(tools / "tcodes.py"),
                        "--group",
                        str(folder),
                        "--frames",
                        "8",
                        "--allow-lower",
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                    timeout=45,
                )
        codes = json.loads((folder / "tcodes.json").read_text())["results"]
        print(
            folder.name,
            "qualified",
            sum(r["repeated_code_candidate"] for r in codes),
            "/",
            len(codes),
            flush=True,
        )


if __name__ == "__main__":
    main()
