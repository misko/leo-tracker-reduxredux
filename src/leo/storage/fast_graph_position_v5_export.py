"""Read-only ALGO06 export composed through the public ALGO05 export port."""

import json
import logging
import shutil
from pathlib import Path

from leo.contracts.fast_graph_position_v5 import MODEL_VERSION
from leo.storage.fast_graph_position import sha
from leo.storage.fast_graph_position_v5 import FastGraphPositionStoreV5
from leo.storage.uri import PathConfinementError

LOGGER = logging.getLogger(__name__)


class FastGraphPositionStoreV5Export(FastGraphPositionStoreV5):
    def completed_inputs(self, *, minimum_completed_utc_ns, include_status=None):
        """Enumerate qualified ALGO06 completions using their own completion time."""
        if (
            not isinstance(minimum_completed_utc_ns, int)
            or isinstance(minimum_completed_utc_ns, bool)
            or minimum_completed_utc_ns <= 0
        ):
            raise ValueError("An explicit positive ALGO06 completion cutoff is required")
        for path in sorted((self.namespace / "jobs").glob("*/status.json")):
            identifier = path.parent.name
            try:
                value = self.status(identifier)
                if (
                    value is None
                    or value["state"] != "complete"
                    or value["updated_utc_ns"] < minimum_completed_utc_ns
                ):
                    continue
                if value["job_id"] != identifier or value["model_version"] != MODEL_VERSION:
                    raise ValueError("ALGO06 status identity differs from its public job")
                # Selection uses status metadata only. Every included job still
                # receives the original complete terminal/input validation.
                if include_status is not None and not include_status(value):
                    continue
                terminal, _ = self.terminal(value)
                if terminal["state"] != "complete":
                    raise ValueError("Completed ALGO06 status lacks its qualified terminal")
                yield value
            except (OSError, ValueError, KeyError, TypeError, PathConfinementError) as error:
                LOGGER.warning(
                    "Rejected completed ALGO06 job %s (%s): %s",
                    identifier,
                    type(error).__name__,
                    error,
                )

    def export_recovery(self, job, destination):
        """Export ALGO05 replay inputs and the unchanged validated ALGO06 terminal.

        The source export is owned and constructed by ALGO05's public port. The
        resulting root is directly consumable by ``algo06_prepare.prepare``.
        """
        status = self.status(job["job_id"])
        if status is None or status["state"] != "complete":
            raise ValueError("Only completed ALGO06 recoveries can be exported")
        incumbent, receipt = self.terminal(job)
        if incumbent["state"] != "complete":
            raise ValueError("Qualified ALGO06 terminal required")
        destination = Path(destination)
        if destination.absolute().is_relative_to(Path("/mnt/qnap01")):
            raise ValueError("QNAP adapters are read-only")
        if destination.is_symlink():
            raise ValueError("Recovery export destination cannot be a symbolic link")
        destination = destination.resolve()
        if destination.is_relative_to(Path("/mnt/qnap01")):
            raise ValueError("QNAP adapters are read-only")
        if destination.is_relative_to(
            self.namespace.resolve()
        ) or self.namespace.resolve().is_relative_to(destination):
            raise ValueError("Recovery export overlaps the production source namespace")
        source_terminal = Path(receipt["path"])
        if source_terminal.is_symlink() or sha(source_terminal) != receipt["sha256"]:
            raise ValueError("ALGO06 incumbent changed before export")
        destination.mkdir(parents=True, mode=0o700, exist_ok=False)
        destination.chmod(0o700)
        source_export = self.incumbent.export_recovery(
            job["source_job"], destination / "source-export"
        )
        if source_export["incumbent"] != incumbent["incumbent"]:
            raise ValueError("ALGO05 export differs from the ALGO06 incumbent")
        target = destination / "algo06-terminal.json"
        shutil.copyfile(source_terminal, target)
        target.chmod(0o600)
        if sha(source_terminal) != receipt["sha256"] or sha(target) != receipt["sha256"]:
            raise ValueError("ALGO06 incumbent changed while exporting")
        current, again = self.terminal(job)
        if current != incumbent or again != receipt:
            raise ValueError("ALGO06 incumbent changed while exporting")
        files = {
            str(Path("source-export") / name): digest
            for name, digest in source_export["files"].items()
        }
        files["source-export/descriptor.json"] = sha(destination / "source-export/descriptor.json")
        files[target.name] = receipt["sha256"]
        descriptor = dict(
            schema_version=1,
            kind="fast-graph-algo06-recovery-export",
            model_version=MODEL_VERSION,
            root=str(destination),
            files=files,
            incumbent=incumbent,
            incumbent_receipt=receipt,
            source_export=source_export,
            source_job=dict(job),
            input_sha256=job["input_sha256"],
            session_id=incumbent["session_id"],
        )
        with (destination / "descriptor.json").open("x") as stream:
            json.dump(descriptor, stream, indent=2, allow_nan=False)
            stream.write("\n")
        return descriptor
