import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
panels = [f"DS{ds}_{part}_8" for ds in (7, 8, 9) for part in ("early", "middle", "late")]
receipts = []
for panel in panels:
    if panel == "DS7_early_8":
        assert (HERE / f"{panel}.json").exists()
        receipt = dict(panel=panel, exit_code=0, execution="completed initial invocation")
    else:
        with (HERE / f"{panel}.log").open("w") as log:
            command = [
                "timeout",
                "90",
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
        receipt = dict(panel=panel, exit_code=result.returncode, execution="bounded invocation")
    receipts.append(receipt)
    (HERE / "receipts.json").write_text(json.dumps(receipts, indent=2) + "\n")
    print(receipt, flush=True)
