"""Freeze and exercise the terminal-only guard on two archived northern offers."""

import argparse
import shutil
from pathlib import Path

from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.qualification.experimental_publication import TERMINAL_VETO_SOURCES
from tools.pipeline_eval.qualification.paired_publication import archive_identity

from .residual_attribution_trial import saved_native
from .screened_stock_salvage_trial import digest, read, require_spec
from .screened_tiled_graph_trial import KEYS, evidence_digests, solve, write
from .sparse_fir_successor import LAUNCHER, RECEIVER, SOURCE, files, options

PARENT = "sha256:6cf354ef58866a795c090d329f0ce87960faaac00e8a146e88c58830aa6f207a"
PARENT_RECEIPT = "3e315fa39419d07a15f1a1684efc7d8da5839421e53a05a66305ba64bcd0b911"
PAIR = "c7117cf8596dd5e14c18914d2db605ce33579f19b25c47ec90e9a4a0af740bf8"
FAR = "dbe95b0cd5a25e9c5d5f5f2df13e52e422348cea1a1dc61429199493ff73649a"
REVIEWED_TERMINAL_CODE = {
    TERMINAL_VETO_SOURCES[1]: "6e7ae57a5762be3028756e3033c070de587c461707dda059692aee5d7c717b96",
    TERMINAL_VETO_SOURCES[3]: "415a098e260d590967ce252b8a497a941c59b600b00f9077723a939932c1ff7e",
}
FLAG = "regional_veto_terminal_only"
FIELDS = (*KEYS, "science")


def freeze(bench, bundle, output):
    parent = bench / "integration-sparse-frame-plane"
    require_spec(parent, PARENT)
    pin = bench / "frame-plane-freeze.json"
    original = read(parent / "spec.json")
    if (digest(pin) != PARENT_RECEIPT or read(pin)["spec"] != original
            or not original["regional_veto"]
            or digest(parent / RECEIVER) != original["detector_sha256"]):
        raise ValueError("Expected the full-guard frame-plane freeze")
    if any(digest(SOURCE / path) != pin for path, pin in REVIEWED_TERMINAL_CODE.items()):
        raise ValueError("Terminal evaluator differs from the reviewed source")
    original_files = files(parent)
    shutil.copytree(parent, bundle, ignore=shutil.ignore_patterns("__pycache__"))
    replacements = {LAUNCHER, TERMINAL_VETO_SOURCES[0], *REVIEWED_TERMINAL_CODE}
    for path in replacements:
        shutil.copyfile(SOURCE / path, bundle / path)
    pins = {str(path): digest(bundle / path) for path in (LAUNCHER, *TERMINAL_VETO_SOURCES)}
    spec = original | {
        FLAG: True, "detector": str(bundle / RECEIVER), "sources": original["sources"] | pins,
    }
    for name, value in original.items():
        if isinstance(value, dict) and set(value) == {"library", "sha256"}:
            library = bundle / Path(value["library"]).relative_to(parent)
            spec[name] = value | {"library": str(library)}
    (bundle / "spec.json").unlink()
    write(bundle / "spec.json", spec)
    identity = canonical_digest(spec)
    require_spec(bundle, identity)
    after = files(bundle)
    changed = {path for path, hash_value in after.items() if original_files.get(path) != hash_value}
    expected = {Path("spec.json"), *replacements}
    if (changed != expected or original_files.keys() - after.keys()
            or options(spec) != options(original) | {FLAG: True}):
        raise ValueError("Terminal guard freeze changed unrelated sources or options")
    write(output, dict(
        specification=identity, parent_specification=PARENT, spec=spec,
        changed_files=sorted(map(str, changed)), inherited_files=len(after) - len(changed),
    ))


def science(result):
    return {name: result.get(name) for name in KEYS} | {"science": evidence_digests(result)}


def compare(control, candidate, withheld):
    if science(control) != science(candidate):
        raise ValueError("Terminal science, ownership or decision changed")
    full, short = (row["regional_bound_guard"] for row in (control, candidate))
    if (not full["evaluated"] or not short["evaluated"] or not full["complete"]
            or full["bound_arms"] != short["bound_arms"]
            or full["would_withhold"] != withheld or short["would_withhold"] != withheld
            or any(len(row["guard_timings"]) != 1 for row in (control, candidate))):
        raise ValueError("Expected a complete matched full and terminal boundary evaluation")
    if withheld:
        if (candidate["status"] != "withheld"
                or candidate["reason"] != "both_receivers_support_far_exterior"
                or candidate["arms"] != {arm: {"latlon": None} for arm in ("c0", "fitted_c")}
                or "evidence" in candidate or "owners" in candidate
                or short["probes_evaluated"] != 96
                or any(short.get(key) != value for key, value in full.items())):
            raise ValueError("Far-omission rule or withholding evidence changed")
    elif (candidate["status"] != "ok" or not science(candidate)["science"]
          or short["complete"] or not 0 < short["probes_evaluated"] < 96):
        raise ValueError("Expected early disproof and the complete inside position")
    return {name: science(row) | {
        key: row[key] for key in ("guard_timings", "solver_cpu_s", "solver_wall_s",
                                  "regional_bound_guard")
    } for name, row in (("full", control), ("terminal", candidate))}


def run(bench, bundle, receipt, output, *, reverse_inside=False):
    parent = bench / "integration-sparse-frame-plane"
    require_spec(parent, PARENT)
    frozen = read(receipt)
    require_spec(bundle, frozen["specification"])
    spec = read(bundle / "spec.json")
    if (frozen["parent_specification"] != PARENT or spec != frozen["spec"] or not spec[FLAG]
            or options(spec) != options(read(parent / "spec.json")) | {FLAG: True}):
        raise ValueError("Expected the frozen terminal-only successor")
    pair_path = bench / "frame-plane-north-inside/pair.json"
    far_path = bench / "frame-plane-offers.json"
    if digest(pair_path) != PAIR or digest(far_path) != FAR:
        raise ValueError("Northern receiver or far-offer receipt changed")
    pair, prior_far = read(pair_path), read(far_path)
    publication = pair["runs"]["candidate"]
    native = saved_native(pair_path, "candidate", publication)
    archive = Path(pair["archive"]["root"])
    native_sha = canonical_digest(native)
    if (pair["candidate_specification_digest"] != PARENT or prior_far["specification"] != PARENT
            or prior_far["archive"] != pair["archive"] or prior_far["pair_sha256"] != PAIR
            or native_sha != prior_far["native_sha256"]
            or archive_identity(archive) != pair["archive"]):
        raise ValueError("Saved detections, offers or causal catalogue differ")

    def replay(variant, offer):
        return solve(variant, native, offer, archive, guard_evidence=True)

    inside = publication["receipt"]["region"]
    scopes = {"full": parent, "terminal": bundle}
    order = ["terminal", "full"] if reverse_inside else ["full", "terminal"]
    inside_runs = {name: replay(scopes[name], inside) for name in order}
    full_inside, short_inside = inside_runs["full"], inside_runs["terminal"]
    valid = compare(full_inside, short_inside, withheld=False)
    published_science = {"grid": valid["full"]["science"]["position_grid"],
                         "path": valid["full"]["science"]["position_path"]}
    if (publication["receipt"]["decision"] != "complete"
            or any(full_inside[key] != publication[key] for key in ("reason", "arms", "owners"))
            or published_science != publication["scientific_digests"]):
        raise ValueError("Complete inside control differs from the raw publication")
    offers = {"north-100m-inside": valid | {"offer": inside, "order": order}}
    if not reverse_inside:
        omitted = prior_far["results"]["north-far"]
        far = omitted["offer"]
        short_far, full_far = replay(bundle, far), replay(parent, far)
        missing = compare(full_far, short_far, withheld=True)
        if science(full_far) != {key: omitted[key] for key in FIELDS}:
            raise ValueError("Full far control differs from the archived saved solve")
        offers["north-far-omitted"] = missing | {"offer": far, "order": ["terminal", "full"]}
    if archive_identity(archive) != pair["archive"]:
        raise ValueError("The causal archive changed during the replays")
    write(output, dict(
        parent_specification=PARENT, specification=frozen["specification"], pair_sha256=PAIR,
        prior_far_sha256=FAR, native_sha256=native_sha, archive=pair["archive"],
        offers=offers,
    ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "solve"))
    for name in ("bench", "bundle", "receipt"):
        parser.add_argument(name, type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--reverse-inside", action="store_true")
    args = parser.parse_args()
    if args.stage == "freeze":
        freeze(args.bench.resolve(), args.bundle.resolve(), args.receipt)
    elif args.output is None:
        parser.error("Expected a saved comparison output")
    else:
        run(args.bench, args.bundle, args.receipt, args.output, reverse_inside=args.reverse_inside)


if __name__ == "__main__":
    main()
