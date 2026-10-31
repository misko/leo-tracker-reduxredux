"""Read-only downstream export port for immutable ALGO04 results."""
import json
import logging
import shutil
from pathlib import Path
from leo.contracts.fast_graph_position_v3 import MODEL_VERSION
from leo.storage.fast_graph_position_v3 import FastGraphPositionStoreV3
from leo.storage.fast_graph_position import sha
from leo.storage.fast_scan import safe_id
from leo.storage.uri import confined_path, PathConfinementError
LOGGER=logging.getLogger(__name__)

class FastGraphPositionStoreV3Export(FastGraphPositionStoreV3):
    def completed_inputs(self, *, minimum_completed_utc_ns):
        """Public downstream port using ALGO04's own completion cutoff.

        Unlike ``inputs``, this enumerates completed ALGO04 jobs, including a new
        recovery whose original ALGO02 baseline predates the downstream cutoff.
        """
        if (
            not isinstance(minimum_completed_utc_ns, int)
            or isinstance(minimum_completed_utc_ns, bool)
            or minimum_completed_utc_ns <= 0
        ):
            raise ValueError("An explicit positive ALGO04 completion cutoff is required")
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
                    raise ValueError("ALGO04 status identity differs from its public job")
                terminal, _ = self.terminal(value)
                if terminal["state"] != "complete":
                    raise ValueError("Completed ALGO04 status lacks its qualified terminal")
                yield value
            except (OSError, ValueError, KeyError, TypeError, PathConfinementError) as error:
                LOGGER.warning(
                    "Rejected completed ALGO04 job %s (%s): %s",
                    identifier,
                    type(error).__name__,
                    error,
                )

    def export_recovery(self, job, destination):
        """Copy a verified private ALGO04 recovery tree for downstream replay.

        JSON bytes and their original path references remain unchanged. The
        consumer must verify this manifest before relocating references in its
        own working copies. Partial exports remain available for diagnosis.
        """
        status = self.status(job["job_id"])
        if status is None or status["state"] != "complete":
            raise ValueError("Only completed ALGO04 recoveries can be exported")
        incumbent, receipt = self.terminal(job)
        if incumbent["state"] != "complete":
            raise ValueError("Qualified ALGO04 terminal required")
        raw_output = self.namespace / "jobs" / safe_id(job["job_id"]) / "output"
        cursor = self.root
        for part in raw_output.relative_to(self.root).parts:
            cursor /= part
            if cursor.is_symlink():
                raise ValueError("Recovery exports cannot traverse symbolic links")
        if (raw_output / "recovery").is_symlink():
            raise ValueError("Recovery exports cannot contain symbolic links")
        source = confined_path(self.namespace, raw_output / "recovery", must_exist=True)
        destination = Path(destination)
        if destination.absolute().is_relative_to(Path("/mnt/qnap01")):
            raise ValueError("QNAP adapters are read-only")
        if destination.is_symlink():
            raise ValueError("Recovery export destination cannot be a symbolic link")
        destination = destination.resolve()
        if destination.is_relative_to(Path("/mnt/qnap01")):
            raise ValueError("QNAP adapters are read-only")
        if (
            destination.is_relative_to(self.namespace.resolve())
            or source.is_relative_to(destination)
            or destination.is_relative_to(source)
        ):
            raise ValueError("Recovery export overlaps the production source namespace")
        destination.mkdir(parents=True, mode=0o700, exist_ok=False)
        destination.chmod(0o700)
        files = {}
        originals = {}
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise ValueError("Recovery exports cannot contain symbolic links")
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = Path("recovery") / path.relative_to(source)
            target = destination / relative
            target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            before = sha(path)
            shutil.copyfile(path, target)
            target.chmod(0o600)
            if sha(path) != before or sha(target) != before:
                raise ValueError("ALGO04 recovery changed while exporting")
            files[str(relative)] = before
            originals[str(path.relative_to(source))] = before
        source_terminal = Path(receipt["path"])
        target = destination / "incumbent-terminal.json"
        shutil.copyfile(source_terminal, target)
        target.chmod(0o600)
        if sha(target) != receipt["sha256"]:
            raise ValueError("ALGO04 incumbent changed while exporting")
        files[target.name] = receipt["sha256"]
        current_paths = {}
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise ValueError("Recovery exports cannot contain symbolic links")
            if path.is_file() and "__pycache__" not in path.parts:
                current_paths[str(path.relative_to(source))] = sha(path)
        current, again = self.terminal(job)
        if current_paths != originals or current != incumbent or again != receipt:
            raise ValueError("ALGO04 recovery or incumbent changed while exporting")
        descriptor = dict(
            schema_version=1,
            kind="fast-graph-recovery-export",
            model_version=MODEL_VERSION,
            root=str(destination),
            source_recovery_root=str(source),
            files=files,
            incumbent=incumbent,
            incumbent_receipt=receipt,
            source_job=dict(job),
            input_sha256=job["input_sha256"],
            session_id=incumbent["session_id"],
        )
        with (destination / "descriptor.json").open("x") as stream:
            json.dump(descriptor, stream, indent=2, allow_nan=False)
            stream.write("\n")
        return descriptor


