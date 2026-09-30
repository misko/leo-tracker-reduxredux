"""Check experiment/source bindings and seal this bounded investigation's artifacts."""

import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "local"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    for result, script in [("identity.json", "corpus_identity.py"),
                           ("within-visit.json", "within_visit.py"),
                           ("stable-specificity.json", "stable_specificity.py")]:
        data = json.loads((OUT / result).read_text())
        assert data["method_sha256"] == sha(BASE / script), result
    identity = json.loads((OUT / "identity.json").read_text())
    rows = json.loads((OUT / "rows.json").read_text())
    assert len(rows) == identity["rows"] == sum(identity["dataset_counts"].values())
    assert len({r["id"] for r in rows}) == len(rows)
    prior = BASE.parent / "2026_09_29_ds10_signal_extension"
    assert identity["metadata_sha256"] == sha(prior / "local/qualified-tracks.json")
    replay = json.loads((OUT / "paired-extension.json").read_text())
    assert replay["script_sha256"] == sha(prior / "paired_recovery.py")
    for r in replay["results"]:
        assert r["state"] in ("exit_0", "reused_existing_summary")
        assert sha(Path(r["summary_path"])) == r["summary_sha256"]
    paths = sorted(BASE.glob("*.py")) + sorted(BASE.glob("*.md"))
    paths += sorted(p for p in OUT.iterdir() if p.is_file() and p.name != "seal.json")
    seal = dict(files={str(p.relative_to(BASE)): sha(p) for p in paths},
                validation="Source bindings, dataset/row counts and paired replay receipts pass. "
                "This is artifact integrity, not proof of semantic decoding.")
    (OUT / "seal.json").write_text(json.dumps(seal, indent=2) + "\n")
    print(f"Validated experiment bindings; sealed {len(paths)} artifacts")


if __name__ == "__main__":
    main()
