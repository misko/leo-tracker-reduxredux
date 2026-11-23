"""Research-only compact publication with staged PNG writes before any PNG fsync."""

from contextlib import ExitStack
import json
import os

from leo.contracts.fast_standard_analysis import COMPACT_MODELS, PLOTS, validate
from leo.contracts.position_grid import binding as grid_binding, validate as validate_grid
from leo.contracts.position_path import validate as validate_path
from leo.storage.fast_scan import immutable_json
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore, digest


class BatchedPngStore(FastStandardAnalysisStore):
    """Keep the production transaction and its private directory rename."""

    def _write_publication(self, folder, run_id, document, pngs, position_grid, position_path):
        model = self.model(run_id)
        if model not in COMPACT_MODELS:
            return super()._write_publication(folder, run_id, document, pngs, position_grid, position_path)
        if document.get("schema_version") == 3 and (position_grid is None or position_path is None):
            raise ValueError("Regional publication requires its objective grid and recorded path")
        folder.mkdir(parents=True, exist_ok=True)
        entries = []
        with ExitStack() as pending:
            descriptors = []
            for name in PLOTS:
                data = pngs[name]
                if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("PNG required")
                checksum = digest(data)
                path = folder / (checksum.removeprefix("sha256:") + ".png")
                if path.exists():
                    if path.read_bytes() != data:
                        raise ValueError("Figure digest collision")
                else:
                    stream = pending.enter_context(path.open("xb"))
                    stream.write(data)
                    stream.flush()
                    descriptors.append(stream.fileno())
                entries.append(dict(name=name, sha256=checksum, byte_count=len(data)))

            for descriptor in descriptors:
                os.fsync(descriptor)

        value = validate(dict(document, artifacts=entries), model=model)
        sidecars = []
        for name, evidence, validator in (("position-grid.json", position_grid, validate_grid),
                                          ("position-path.json", position_path, validate_path)):
            if evidence is not None:
                checked = validator(dict(evidence, binding=grid_binding(value)), value)
                raw = json.dumps(checked, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
                sidecars.append((name, dict(document=checked, sha256=digest(raw))))
        for name, evidence in sidecars:
            immutable_json(folder / name, evidence)
        immutable_json(folder / "manifest.json", value)
        return value
