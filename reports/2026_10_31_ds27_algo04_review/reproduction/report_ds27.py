"""Sealed DS27 reporting; geographic truth is introduced only after hash checks."""
import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

from rank_native_residuals import published_owners


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def chosen_arms(terminal):
    if terminal["model_version"] == "algo04-causal-numerical-v1":
        return chosen_arms(terminal["candidate"] if terminal["decision"] == "ALGO04_additive" else terminal["incumbent"])
    if terminal["model_version"] == "algo03-causal-predictive-v1":
        return terminal["selected"]["arms"] if terminal.get("selected") else chosen_arms(terminal["baseline"])
    if terminal["model_version"] == "algo02-causal-family-v1":
        return terminal["arms"]
    raise ValueError("Unknown terminal model")


def distance(position, truth):
    lat, lon, tlat, tlon = map(math.radians, (*position, *truth))
    a = math.sin((lat-tlat)/2)**2 + math.cos(lat)*math.cos(tlat)*math.sin((lon-tlon)/2)**2
    return 12742.0176 * math.atan2(math.sqrt(a), math.sqrt(max(0, 1-a)))


def verify_index(index, seal, dataset=None):
    if digest(index) != read(seal)["analysis_index_sha256"]:
        raise ValueError("Analysis index changed after inference seal")
    doc = read(index)
    if len({r["case"] for r in doc["cases"]}) != len(doc["cases"]):
        raise ValueError("Duplicate cases")
    if dataset is not None:
        if digest(dataset) != read(seal)["dataset_execution_manifest_sha256"]:
            raise ValueError("Execution membership changed")
        manifest = read(dataset)
        if digest(manifest["manifest_path"]) != manifest["manifest_sha256"]:
            raise ValueError("Dataset membership changed")
        expected = {r["case"]: r for r in manifest["cases"] if r["recording_format"] == "short_window_iq_recording"}
        if set(expected) != {r["case"] for r in doc["cases"]}:
            raise ValueError("Missing or extra fast cases in analysis index")
        for entry in doc["cases"]:
            if entry["recording_id"] != expected[entry["case"]]["recording_id"]:
                raise ValueError("Different recording identity")
    for row in doc["cases"]:
        if row["state"] not in ("complete", "unavailable", "failed"):
            raise ValueError("Unfinished inference")
        if row["state"] == "complete":
            for name in ("terminal", "tracks", "observations"):
                if digest(row[name+"_path"]) != row[name+"_sha256"]:
                    raise ValueError("Changed inference input: "+row["case"]+"/"+name)
    return doc


def case_rows(entry, truth):
    if entry["state"] != "complete":
        return [dict(case=entry["case"], method=m, arm=a, state=entry["state"], reason=entry.get("reason"))
                for m in ("ALGO02", "ALGO03", "ALGO04") for a in ("c0", "fitted_c")]
    terminal = read(entry["terminal_path"])
    if terminal["model_version"] != "algo04-causal-numerical-v1":
        raise ValueError("ALGO04 terminal required")
    from leo.contracts.fast_graph_position_v3 import validate_terminal
    validate_terminal(terminal, input_sha256=entry["input_sha256"])
    observations = read(entry["observations_path"])
    all_ids = {o["observation_id"] for o in observations}
    if len(all_ids) != len(observations):
        raise ValueError("Duplicate GLRT identities")
    v2 = terminal["incumbent"]
    methods = {"ALGO02": v2["baseline"], "ALGO03": v2, "ALGO04": terminal}
    result = []
    for method, value in methods.items():
        if set(chosen_arms(value)) != {"c0", "fitted_c"}:
            raise ValueError("Missing matched c arm")
        for arm, fit in chosen_arms(value).items():
            if arm not in ("c0", "fitted_c"):
                continue
            owners = published_owners(value, arm)
            if method == "ALGO02":
                # V1 linear gates can omit NORAD; the V2 proof resolves exactly
                # those published IDs without importing unpublished post-fit IDs.
                proof = v2["source_support"][arm]["owners"]
                if set(proof) != set(owners) or any(n is not None and proof[i] != n for i, n in owners.items()):
                    raise ValueError("ALGO02 ownership proof differs from published IDs or known labels")
                owners = dict(proof)
            if not set(owners) <= all_ids:
                raise ValueError("Unknown associated observation")
            old = published_owners(v2, arm)
            if method == "ALGO04" and any(owners.get(i) != n for i, n in old.items()):
                raise ValueError("ALGO04 lost incumbent owners")
            result.append(dict(case=entry["case"], method=method, arm=arm, state="complete",
                reason=None, decision=value.get("decision"), glrt_points=len(all_ids), associated=len(owners),
                associated_percent=100*len(owners)/len(all_ids), families=len(set(owners.values())),
                error_km=distance(fit["endpoint_latlon"], truth),
                endpoint_latitude=fit["endpoint_latlon"][0], endpoint_longitude=fit["endpoint_latlon"][1],
                frequency_rms_hz=fit.get("RMS_hz"), frequency_objective=fit.get("negative_twice_elbo"),
                support_sha256=hashlib.sha256(json.dumps(owners, sort_keys=True).encode()).hexdigest()))
    return result


def c_ablation(rows):
    """Position on all pairs; fit differences only for exact common ownership."""
    import numpy as np
    result = {}
    for method in ("ALGO02", "ALGO03", "ALGO04"):
        lookup = {(r["case"], r["arm"]): r for r in rows if r["method"] == method and r["state"] == "complete"}
        pairs = [(v, lookup[(c, "fitted_c")]) for (c, a), v in lookup.items() if a == "c0"]
        same = [(a, b) for a, b in pairs if a["support_sha256"] == b["support_sha256"]]
        item = dict(paired_scans=len(pairs), identical_support_pairs=len(same),
                    different_support_pairs=len(pairs)-len(same))
        item["mean_fitted_minus_c0_error_km"] = float(np.mean([b["error_km"]-a["error_km"] for a, b in pairs])) if pairs else None
        for name in ("frequency_rms_hz", "frequency_objective"):
            differences = [b[name]-a[name] for a, b in same if a[name] is not None and b[name] is not None]
            item[name+"_comparable_pairs"] = len(differences)
            item["mean_fitted_minus_c0_"+name] = float(np.mean(differences)) if differences else None
        result[method] = item
    return result


def summarize(rows):
    import numpy as np
    result = {}
    for method in ("ALGO02", "ALGO03", "ALGO04"):
        result[method] = {}
        for arm in ("c0", "fitted_c"):
            selected = [r for r in rows if r["method"] == method and r["arm"] == arm]
            good = [r for r in selected if r["state"] == "complete"]
            if not good:
                result[method][arm] = dict(total=len(selected), complete=0)
                continue
            errors = [r["error_km"] for r in good]
            total, associated = sum(r["glrt_points"] for r in good), sum(r["associated"] for r in good)
            result[method][arm] = dict(total=len(selected), complete=len(good), glrt_points=total,
                associated=associated, pooled_associated_percent=100*associated/total,
                mean_error_km=float(np.mean(errors)), median_error_km=float(np.median(errors)),
                p95_error_km=float(np.percentile(errors, 95)), worst_error_km=max(errors),
                within_500m=sum(e <= .5 for e in errors))
    return result


def figures(rows, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    good = [r for r in rows if r["state"] == "complete"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
    styles = dict(ALGO02=(".5", "--"), ALGO03=("tab:blue", ":"), ALGO04=("tab:orange", "-"))
    for ax, arm in zip(axes, ("c0", "fitted_c")):
        for method, (color, style) in styles.items():
            errors = sorted(r["error_km"] for r in good if r["method"] == method and r["arm"] == arm)
            ax.step(errors, np.arange(1, len(errors)+1)/len(errors), where="post", label=method, color=color, ls=style)
        ax.axvline(.5, color=".5", alpha=.4)
        ax.set(title="c = 0" if arm == "c0" else "Fitted c", xlabel="Position error (km)", ylabel="Fraction of available scans", ylim=(0, 1.02))
        ax.grid(alpha=.2)
        ax.legend()
    fig.suptitle("DS27 fast scans: matched c arms, unavailable scans excluded from CDF")
    fig.savefig(output/"position-error-cdf.png", dpi=160)
    plt.close(fig)
    cases = sorted({r["case"] for r in good})
    fig, axes = plt.subplots(3, 1, figsize=(14, 11), sharex=True, layout="constrained")
    for ax, arm in zip(axes[:2], ("c0", "fitted_c")):
        for method, (color, style) in styles.items():
            lookup = {r["case"]: r for r in good if r["method"] == method and r["arm"] == arm}
            ax.plot(range(len(cases)), [lookup[c]["error_km"] for c in cases], marker="o", ms=4, label=method, color=color, ls=style)
        ax.axhline(.5, color=".5", alpha=.4)
        ax.set(ylabel="Position error (km)", title="c = 0" if arm == "c0" else "Fitted c")
        ax.legend(ncol=3)
        ax.grid(alpha=.2)
    for method, (color, style) in styles.items():
        lookup = {r["case"]: r for r in good if r["method"] == method and r["arm"] == "fitted_c"}
        axes[2].plot(range(len(cases)), [lookup[c]["associated_percent"] for c in cases], marker="o", ms=4, label=method, color=color, ls=style)
    axes[2].set(ylabel="GLRT associated (%)", title="Fitted-c published ownership", xticks=range(len(cases)), xticklabels=[c.replace("DS27-", "") for c in cases], xlabel="DS27 scan")
    axes[2].legend(ncol=3)
    axes[2].grid(alpha=.2)
    fig.savefig(output/"per-scan-errors-and-coverage.png", dpi=160)
    plt.close(fig)


def report(index, seal, output):
    sys.path.insert(0, "/opt/leo-fast-graph/f9e262f96b6e2e75b397f69d50a0ea9104e293ef/src")
    doc = verify_index(index, seal, index.parent/"datasets/DS27.json")
    # Unexpected pipeline failures require a method-specific report, not erasing valid comparators.
    if any(r["state"] != "complete" and r.get("baseline_terminal_path")
           and read(r["baseline_terminal_path"]).get("state") == "complete" for r in doc["cases"]):
        raise ValueError("Available comparator without ALGO04: method-specific availability review required")
    # User-confirmed evaluation site; only accessed after all inference hashes verify.
    truth = (37.849061591561885, -122.48574968092912)
    rows = [r for entry in doc["cases"] for r in case_rows(entry, truth)]
    output.mkdir(parents=True, exist_ok=False)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (output/"per-case.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = dict(schema="ds27-sealed-report/v1", evaluation_site=truth,
                   analysis_index_sha256=digest(index), inference_seal_sha256=digest(seal),
                   summary=summarize(rows), c_ablation=c_ablation(rows))
    (output/"summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    figures(rows, output)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--seal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report(args.index, args.seal, args.output)
