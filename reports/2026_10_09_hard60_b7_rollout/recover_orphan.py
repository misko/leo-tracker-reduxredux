"""Fenced operator retry of the one exited migration attempt; preserve its failure."""

import json
import subprocess
from pathlib import Path

from sqlalchemy import text

from leo.catalog import CatalogRepository, create_catalog_engine, create_session_factory

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    assert not Path("/proc/211692").exists(), "The failed worker must have exited"
    pid = subprocess.check_output(
        [
            "systemctl",
            "show",
            "leo-adaptive-analysis-worker@24.service",
            "-p",
            "MainPID",
            "--value",
        ],
        text=True,
    ).strip()
    env = dict(
        item.split("=", 1)
        for item in Path(f"/proc/{pid}/environ").read_text().split("\0")
        if "=" in item
    )
    assert env["PYTHONPATH"].startswith("/opt/leo-b7/88e231eb1-r1/worker/src")
    engine = create_catalog_engine(env["LEO_DATABASE_URL"])
    try:
        with engine.connect() as connection:
            rows = [
                dict(r)
                for r in connection.execute(
                    text(
                        "SELECT id,adaptive_session_id,adaptive_input_manifest_digest,"
                        "adaptive_configuration_digest,state,lease_owner,"
                        "attempt_count,max_attempts "
                        "FROM processing_job WHERE id IN (48940,48942) ORDER BY id"
                    )
                ).mappings()
            ]
        old, replacement = rows
        assert old["state"] == "leased"
        assert old["lease_owner"] == "adaptive-worker-24-4f75e3ea88ea"
        assert old["attempt_count"] < old["max_attempts"]
        assert replacement["state"] in ("pending", "leased", "succeeded")
        for key in ("adaptive_session_id", "adaptive_input_manifest_digest"):
            assert old[key] == replacement[key]
        assert old["adaptive_configuration_digest"] != replacement["adaptive_configuration_digest"]
        repository = CatalogRepository(create_session_factory(engine))
        result = repository.fail_job(
            job_id=48940,
            worker_id=old["lease_owner"],
            retryable=True,
            error="Operator recovery: exited policy-migration worker hit VARCHAR(32); "
            "replacement job 48942 exists; corrected workers may retry the old handoff.",
        )
        receipt = dict(
            actor="explicit operator recovery, not a worker heartbeat",
            exited_pid=211692,
            before=rows,
            result=str(result),
            mutation="CatalogRepository.fail_job with exact original owner fence",
        )
        Path("/tmp/b7-orphan-recovery.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(dict(job_id=48940, result=str(result))))
    finally:
        engine.dispose()
