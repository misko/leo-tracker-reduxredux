"""Postseal reporting only; never reconstruct observations or run an objective."""

import hashlib
import json
import runpy
from pathlib import Path

from report_downstream import load_records, slice_summary, summarize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluation_callback(plan, records):
    # Check seal BEFORE importing the public reference port or reading its document.
    if not all(
        records[b]["status"] in {"complete", "failed", "budget-exhausted"}
        for b in ("native", "fixed")
    ):
        raise ValueError("both branches must seal before reference access")
    authority = ROOT / "reports/2026_10_09_position_error_iter107/protocol.json"
    key = str(authority.relative_to(ROOT))
    if sha(authority) != plan["input_sha256"][key]:
        raise ValueError("evaluation membership authority changed")
    previous = json.loads(authority.read_text())
    members = [
        m
        for m in previous["members"]
        if m["member"].get("inventory_label", m["member"].get("dataset_label")) == "DS18-022"
    ]
    if len(members) != 1:
        raise ValueError("ambiguous evaluation member")
    report = runpy.run_path(str(authority.parent / "report.py"))
    document = report["evaluation_document"](members[0])
    sanitized = json.loads((ROOT / plan["binding"]["document_path"]).read_text())
    for name in ("session_id", "input_manifest_sha256", "evidence_sha256"):
        if document[name] != sanitized[name]:
            raise ValueError("evaluation input authority mismatch: " + name)
    if document["configuration"]["prior"] != sanitized["configuration"]["prior"]:
        raise ValueError("evaluation regional prior differs from inference")

    def evaluate(branch, arm, operation):
        value = report["evaluate_fit"](operation, document)
        return {key: value[key] for key in ("error_km",)}

    return evaluate, dict(
        authority_sha256=sha(authority),
        evaluation_report_sha256=sha(authority.parent / "report.py"),
        document_binding=members[0]["sources"],
    )


def build():
    from leo.contracts.digests import canonical_digest

    plan = json.loads((HERE / "protocol.json").read_text())
    digest = canonical_digest(plan)
    records, hashes = load_records(HERE / "results", digest)
    evaluate, binding = evaluation_callback(plan, records)
    result = summarize(records, evaluate=evaluate)
    result.update(
        protocol_sha256=digest,
        protocol_file_sha256=sha(HERE / "protocol.json"),
        receipt_sha256=hashes,
        evaluation_binding=binding,
        slices=slice_summary(HERE / "results", digest),
    )
    return result


def plot(result, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    arms = ("fitted-c", "zero-c")
    for index, branch in enumerate(("native", "fixed")):
        for armindex, arm in enumerate(arms):
            endpoint = result["branches"][branch]["arms"][arm]
            x = index + (-0.16 if armindex == 0 else 0.16)
            color = "#3366a3" if armindex == 0 else "#d78232"
            if "position_evaluation" in endpoint:
                axes[0].bar(
                    x,
                    endpoint["position_evaluation"]["error_km"],
                    0.28,
                    color=color,
                    label=arm if index == 0 else None,
                )
            if "frequency" in endpoint:
                axes[1].bar(x, endpoint["frequency"]["posterior_rms_hz"], 0.28, color=color)
    for axis in axes:
        axis.set_xticks([0, 1], ["Native discovery", "Fixed-bank discovery"])
        axis.grid(axis="y", alpha=0.2)
        axis.set_axisbelow(True)
    axes[0].set_ylabel("Position error (km), evaluation only")
    axes[1].set_ylabel("Selected frequency RMS (Hz)")
    axes[0].legend()
    fig.suptitle("DS18-022 · matched downstream research controls · consumed case")
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    result = build()
    # New report outputs are exclusive; never overwrite a published receipt.
    with (HERE / "DOWNSTREAM_SUMMARY.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    plot(result, HERE / "downstream-comparison.png")
