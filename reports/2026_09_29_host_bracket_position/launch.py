"""Run the frozen nine panels sequentially with explicit timeout receipts."""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
receipts = []
for ds in ("DS7", "DS8", "DS9"):
    for block in ("early", "middle", "late"):
        key = f"{ds}_{block}_8"
        with (HERE / f"{key}.log").open("w") as log:
            try:
                p = subprocess.run(
                    [sys.executable, str(HERE / "run.py"), key],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=120,
                )
                receipt = dict(unit=key, exit_code=p.returncode, timeout=False)
            except subprocess.TimeoutExpired:
                receipt = dict(unit=key, exit_code=None, timeout=True)
        receipts.append(receipt)
        (HERE / "receipts.json").write_text(json.dumps(receipts, indent=2) + "\n")
        print(receipt, flush=True)
