"""Execute only the committed metadata mint after validating its frozen closure."""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    raw = (HERE / "protocol.json").read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "0e93118d9449cc2571aadbb0148365663acbed1d1b15eff60ff7a17396c02de0"
    )
    plan = json.loads(raw)
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected, name
    assert not (HERE / "local").exists()
    base = [
        "sudo",
        "-n",
        "-u",
        "leo",
        "env",
        "PYTHONPATH=" + plan["frozen_api_pythonpath"],
        plan["python_executable"],
        plan["mint_source"],
    ]
    arguments = [
        "--dataset-id",
        plan["dataset_id"],
        "--parent-dataset",
        plan["parent_dataset"],
        "--parent",
        plan["parent_authority"],
        "--start",
        plan["start"],
        "--end",
        plan["end"],
        "--output",
        plan["output"],
    ]
    receipts = []
    for action in ("mint", "verify"):
        command = base + [action] + arguments
        begun = datetime.now(UTC).isoformat()
        result = subprocess.run(command, capture_output=True, text=True)
        receipts.append(
            dict(
                action=action,
                argv=command,
                started_utc=begun,
                finished_utc=datetime.now(UTC).isoformat(),
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        )
        (HERE / "mint-execution.json").write_text(
            json.dumps(
                dict(
                    protocol_sha256=hashlib.sha256(raw).hexdigest(),
                    closure_files_verified=len(plan["source_sha256"]),
                    prepared_commit="15e7ef869",
                    operations=receipts,
                ),
                indent=2,
            )
            + "\n"
        )
        assert result.returncode == 0, result.stderr
    print(receipts[-1]["stdout"])


if __name__ == "__main__":
    main()
