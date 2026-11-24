"""Measure the merged audit writer on the already qualified original tiny input."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from legacy_block_0107_metadata import checked, digest, direct_tmpfs, metadata


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = "133b6374d8a449035676c0cb7766ae79c175a1de"
PRIOR = Path("/dev/shm/leo-v3-legacy-all-0107-result01")
PRIOR_PIN = "c86a21b1555be7d4cc6ef61e2f416dc9b89c40ab647e35eaaa55ea4c40289122"
AUDIT = "legacy-map-acquisition.json"
AUDIT_PIN = "0665e8456d1d002fe601963bb47274282ed3b7f52f9969bbacdf7312af8f1213"
CHANGED = {
    "reports/ALGO08/v3/legacy_block_raw_entry.py": "sha256:1eccf6d5529965a3587e2a001613f4f5eb174949facd9676663823ee7dc29a64",
    "reports/ALGO08/v3/legacy_block_multi.py": "sha256:f987c3ffdcb31221a664a3a8f029c457c1b2b91e8c9349f6f86d0f85da69e6e4",
    "reports/ALGO08/v3/legacy_map_receipt.py": "sha256:8a9155c1219fa1b88d9a547c12483dddcc6a245ca8c47061407b49f8e567387b",
}


def audited_payload(audit):
    """Remove only actual stopwatch and resource readings from the cross-run comparison."""
    timer = {"wall_ns", "cpu_ns", "input_blocks"}
    clocks = ("auth", "metadata", "setup", "span_decode", "map_file")
    if set(audit["setup"]) != {"cpu_s", "elapsed_s"}:
        raise ValueError("The legacy audit setup schema changed")
    rows = []
    for source in audit["members"]:
        if any(set(source[name]) != timer for name in clocks):
            raise ValueError("The measured map audit must keep the same known stopwatch fields")
        rows.append({key: value for key, value in source.items() if key not in clocks})
    return {key: value for key, value in audit.items() if key not in ("setup", "members")} | {"members": rows}


def load(path):
    return json.loads(path.read_bytes())


def prior_run():
    scored = json.loads(checked(direct_tmpfs(PRIOR/"result.json"), PRIOR_PIN))
    if not scored["qualified"] or scored["same_terminal"]["science"]["reason"] != "no_active_curvature":
        raise ValueError("Expected the qualified all-member withholding control")
    return scored


def seal(root):
    return {str(path.relative_to(root)): digest(path.read_bytes()) for path in root.rglob("*") if path.is_file()
            and path.relative_to(root).parts[0] not in ("fonts", "tmp")
            and path.name not in ("prediction-seal.json", "result.json", "old-writer-replay.json")}


def launch(root):
    import empty_bootstrap as boot

    sys.path.extend((str(ROOT), str(boot.RELEASE/"src"), str(boot.RELEASE)))
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_0107_pair import verified_scope
    from eight_ms_south_transfer import environment_for
    from exact_named_raw import staged_path
    from raw_0016_best_trial import measure_mode
    from visit_frame_raw_0016 import resident

    start = boot.now()
    if root.exists() or direct_tmpfs(root.parent) != Path("/dev/shm"):
        raise ValueError("Use a fresh private output beside the original tmpfs witness")
    old = prior_run()["admission"]
    identity = load(PRIOR/"indexed-clock.json")
    if identity["command"] != old["command"] or identity["clock"]["exit_code"]:
        raise ValueError("The archival child was not the enrolled complete ordinary-I/Q control")
    legacy = json.loads(checked(PRIOR/"indexed"/AUDIT, AUDIT_PIN))
    machine = host()
    if machine != load(PRIOR.parent/"leo-v3-legacy-block-0107-result01/admission.json")["machine"]:
        raise ValueError("Use the previously verified host settings")
    for args in (["rev-parse", BASE], ["merge-base", "--is-ancestor", BASE, "HEAD"]):
        subprocess.run(["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), *args], capture_output=True, check=True)
    runtime = old["source_pins"] | CHANGED
    for rel, pin in runtime.items():
        checked(direct_tmpfs(ROOT/rel), pin)
    request = old["request"]
    rec = Path(request["recording"])
    arrived = metadata(ROOT)
    if arrived["request"] != request or arrived["files"] != old["metadata"]["files"]:
        raise ValueError("Original signed metadata or archive was modified")
    verified_scope(Path(arrived["signed_stage"]), rec)
    all_files = [staged_path(Path(row["path"]), root=rec) for row in arrived["files"].values()]
    waveform = resident(all_files)
    map_root = PRIOR/"maps"
    plan = json.loads(checked(direct_tmpfs(map_root/"custody.json"), old["plan_pin"]))
    row, = plan["members"]
    audited, = legacy["members"]
    if (plan != old["active_plan"] or row["map_kind"] != "literal" or audited["map_sha256"] != row["map_sha256"]
            or legacy["binary_sha256"] != old["decoder_sha256"]):
        raise ValueError("The earlier authenticated literal map and decoder must remain exact")
    checked(direct_tmpfs(map_root/row["map"]), row["map_sha256"])
    checked(direct_tmpfs(map_root/"legacy-block.so"), old["decoder_sha256"])
    map_ready = resident([map_root/"custody.json", map_root/row["map"], map_root/"legacy-block.so"])
    root.mkdir(mode=0o700)
    (root/"tmp").mkdir()
    shutil.copytree(PRIOR/"fonts", root/"fonts")
    command = list(identity["command"])
    command[5] = str(HERE/"legacy_block_all_entry.py")
    command[command.index("--output")+1] = str(root/"indexed")
    write(root/"admission.json", dict(base=BASE, source_pins=runtime, changes=CHANGED, prior_sha256=PRIOR_PIN,
          request=request, metadata=arrived, command=command, original=waveform, map_ready=map_ready,
          map_payload_sha256=row["map_sha256"], custody_sha256=old["plan_pin"], decoder_sha256=old["decoder_sha256"],
          machine=machine, admission=boot.clock(start), raw_preparation_bytes=0, ordinary_children=0))
    try:
        measure_mode(root, "indexed", command, environment_for(root), lambda: resident(all_files))
    finally:
        write(root/"prediction-seal.json", seal(root))


def score(root):
    sys.path[:0] = [str(ROOT/"src"), str(ROOT)]
    from aperture_trial import write
    from exact_named_raw import write as encode_before
    from legacy_block_0107_score import snapshot

    measured, book = (load(root/name) for name in ("indexed-clock.json", "admission.json"))
    if (measured["command"] != book["command"] or load(root/"prediction-seal.json") != seal(root)
            or book["prior_sha256"] != PRIOR_PIN):
        raise ValueError("The measured process or finalized publication changed")
    for path, pin in book["source_pins"].items():
        checked(ROOT/path, pin)
    prior = prior_run()
    clock = measured["clock"]
    context = snapshot(root/"indexed", clock, book["request"])
    before = prior["same_terminal"]
    if any(context[field] != before[field] for field in ("terminal", "native_digest", "scan_digest", "graph_proof", "receiver_visits", "factors")):
        raise ValueError("Both original physical measurements must have identical signed science and zero position artifacts")
    rows = [list(folder.glob("fast-scan-automatic-work/*/detections.json")) for folder in (root/"indexed", PRIOR/"indexed")]
    if any(len(group) != 1 for group in rows) or rows[0][0].read_bytes() != rows[1][0].read_bytes():
        raise ValueError("The actual native byte strings must agree")
    old_audit = json.loads(checked(PRIOR/"indexed"/AUDIT, AUDIT_PIN))
    body = (root/"indexed"/AUDIT).read_bytes()
    new_audit = json.loads(body)
    if audited_payload(new_audit) != audited_payload(old_audit):
        raise ValueError("The map audit's signed support and verification work changed")
    old_format = root/"old-writer-replay.json"
    encode_before(old_format, new_audit, scientific=True)
    if old_format.read_bytes() != body:
        raise ValueError("The formerly used scientific encoder must reproduce the fresh audit byte for byte")
    prices = {metric: dict(prior_child=prior["process"][metric], current_child=clock[metric],
              observed_saving=prior["process"][metric]-clock[metric], preflight=book["admission"][metric],
              with_preflight=clock[metric]+book["admission"][metric], ordinary=prior["prior_ordinary"][metric])
              for metric in ("elapsed_s", "cpu_s")}
    write(root/"result.json", dict(qualified=True, case="DS30-0107", admission=book, scope=dict(raw_children=1,
          map_preparation_reads=0, comparisons_reused=True), fresh_process=clock, prior_all_member=prior["process"],
          prices=prices, proof=context, audit=new_audit, old_audit_sha256=AUDIT_PIN, new_audit_sha256=digest(body),
          same_encoder_bytes=True, same_audit_fields_except_live_measurements=True,
          prediction_sha256=digest((root/"prediction-seal.json").read_bytes())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "score"))
    parser.add_argument("root", type=Path)
    opts = parser.parse_args()
    {"launch": launch, "score": score}[opts.action](opts.root)
