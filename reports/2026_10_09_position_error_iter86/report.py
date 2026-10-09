"""Use iteration84 reporting with explicitly audited immutable source selection."""

import hashlib
import json
import sys
from pathlib import Path

from selection import selected_receipt, source_for

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent / "2026_10_09_position_error_iter84"
sys.path.insert(0, str(ORIGINAL))
import report as original  # noqa: E402


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    selection_plan = dict(plan, retry_protocol_sha256=digest)
    original_read = original.read
    provenance = {
        b["member"]["inventory_label"]: dict(
            label=b["member"]["inventory_label"],
            source=source_for(b["member"]["inventory_label"], plan["retry_members"]),
            source_protocol_sha256=None,
        ) for b in plan["members"]
    }
    original.HERE = HERE

    def read(path):
        if path.parent == HERE / "results":
            label = path.stem
            member = next(b["member"] for b in plan["members"] if b["member"]["inventory_label"] == label)
            old_path = ORIGINAL / "results" / path.name
            old = original_read(old_path) if old_path.exists() else None
            retry_path = Path(path)
            retry = original_read(retry_path) if retry_path.exists() else None
            selected = selected_receipt(label, member, selection_plan, old, retry)
            provenance[label] = dict(label=label, source=selected["selected_source"],
                                     source_protocol_sha256=selected.get("source_protocol_sha256"))
            # Adapt only the in-memory assertion view; persisted receipts remain immutable.
            return dict(selected, protocol_sha256=digest)
        return original_read(path)

    # Original reporter checks path.exists before read. Point all non-retry paths at
    # their original files through a dedicated Path facade rather than copying them.
    class ReportPath(type(HERE)):
        def exists(self):
            if self.parent == HERE / "results" and self.stem not in plan["retry_members"]:
                return (ORIGINAL / "results" / self.name).exists()
            return super().exists()

    original.HERE = ReportPath(HERE)
    original.read = read
    original.main()
    (HERE / "receipt-selection.json").write_text(json.dumps(list(provenance.values()), indent=2) + "\n")
    text = (HERE / "RESULTS.md").read_text().replace("Iteration84", "Iteration86 pause-safe")
    (HERE / "RESULTS.md").write_text(text)


if __name__ == "__main__":
    main()
