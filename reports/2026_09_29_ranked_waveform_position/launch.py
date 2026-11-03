import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
receipts = []
for ds in (7, 8, 9):
    for part in ("early", "middle", "late"):
        panel = f"DS{ds}_{part}_8"
        with (HERE / f"{panel}.log").open("w") as log:
            command = [
                "timeout",
                "60",
                "uv",
                "run",
                "--no-project",
                "--with",
                "numpy",
                "--with",
                "scipy",
                "python",
                str(HERE / "run.py"),
                panel,
            ]
            result = subprocess.run(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=dict(os.environ, OPENBLAS_NUM_THREADS="1"),
            )
        receipt = dict(panel=panel, exit_code=result.returncode)
        receipts.append(receipt)
        (HERE / "receipts.json").write_text(json.dumps(receipts, indent=2) + "\n")
        print(receipt, flush=True)
