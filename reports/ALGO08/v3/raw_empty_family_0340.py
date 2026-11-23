"""Run one warm-only original 0340 regression for the empty-family calibration guard."""

import argparse
import json
import os
from pathlib import Path
import subprocess

from empty_bootstrap import checked
from raw_0016_best_trial import HERE, measure_mode, sha
from raw_cfo_0016_trial import receiver_preflight


BASE = "efb3590de1f9b825f20df6a2123ce75f4664a71f"
FLAG = "--withhold-empty-family-calibration"
PRIOR = Path("/dev/shm/leo-v3-raw-combined-0340-result01")
PRIOR_SHA = "865d739da0c028c0b14f7ef8100c8026e50cd781841b0d60fc69fe96aa4eb82c"
SAVED = Path("/dev/shm/leo-family-control-0340-candidate")
SAVED_SHA = "4e991b1bef55aaa43e77632010809d9913f8bef669554f421a1a1fc982ff4216"
NATIVE_SHA = "8b40d6afa2a87d87575f3896699e66e907bfede9f9a86deab9a6001132469ce7"
TERMINAL_SHA = "f44862cbdd8927c55339d40dc952b02288ec0298fe7c5591192871fce0d4a3de"
CHANGED = ("joint_publication.py", "unified_short_bootstrap.py")
GUARD = "empty_family_calibration.py"
PAGES = 167_593
MEMBERS = 9


def original():
    witness = json.loads(checked(PRIOR/"prediction-seal.json", PRIOR_SHA))

    def bound(name):
        return json.loads(checked(PRIOR/name, witness[name]))

    return bound("admission.json"), bound("candidate-clock.json")


def source_pins(previous):
    repo = HERE.parents[2]
    unchanged = {name: digest for name, digest in previous.items() if name not in CHANGED}
    for name, digest in unchanged.items():
        checked(HERE/name, digest)
    added = {}
    for name in (*CHANGED, GUARD):
        path = HERE/name
        frozen = subprocess.check_output(["git", "-c", f"safe.directory={repo}", "-C", repo,
                                          "show", f"{BASE}:{path.relative_to(repo)}"])
        added[name] = sha(frozen)
        checked(path, added[name])
    return unchanged | added


def command(root, original_command):
    argv = list(original_command)
    if Path(argv[2]).name != "short_cfo_raw.py" or FLAG in argv:
        raise ValueError("Expected the original refined raw command without the new guard")
    argv[2] = str(HERE/"short_cfo_raw.py")
    argv[argv.index("--output")+1] = str(root/"candidate")
    argv.append(FLAG)
    return argv


def fully_resident(counts):
    return (counts["cached_pages"] == counts["observed_file_pages"] == PAGES
            and counts["members"] == counts["observed_members"] == MEMBERS and not counts["unavailable"])


def seal(root):
    paths = [root/name for name in ("admission.json", "preflight.json", "candidate-clock.json", "candidate.stdout", "candidate.stderr")]
    paths.extend(path for path in (root/"candidate").rglob("*") if path.is_file())
    return {str(path.relative_to(root)): sha(path.read_bytes()) for path in sorted(paths)}


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import CACHE_LIB, CACHE_SHA, FastScanStore, cache_residency, pairs

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Expected a fresh private tmpfs output")
    previous, timed = original()
    pins = source_pins(previous["sources"])
    saved = json.loads(checked(SAVED/"calibration-trial.json", SAVED_SHA))
    if saved["guard_sha256"] != pins[GUARD] or timed["clock"]["exit_code"] == 0:
        raise ValueError("Expected the previously failed raw command and the matching saved guard")
    checked(PRIOR/"offer.json", previous["offer_sha256"])
    if pairs.archive_identity(PRIOR/"tle")["snapshots_sha256"] != previous["archive"]["sha256"]:
        raise ValueError("The original staged causal archive changed")
    for name, digest in previous["library_sha256"].items():
        checked(PRIOR/(name+".so"), digest)
    checked(CACHE_LIB, CACHE_SHA)
    query = cache_residency.load_query(CACHE_LIB)
    manifests = tuple((Path(row["path"]), row["sha256"]) for row in previous["manifests"])
    store = FastScanStore(root)

    def snapshot():
        return cache_residency.bound_snapshot(store, Path(previous["recording"]), manifests, os.sysconf("SC_PAGE_SIZE"), query)

    def resident():
        pages = snapshot()
        if not fully_resident(pages):
            raise ValueError(f"Original 0340 is no longer fully resident. No warming or retry: {pages}")
        return pages

    before = snapshot()
    root.mkdir(mode=0o700)
    write(root/"admission.json", dict(base=BASE, host=machine, passive_pages=before, original_seal_sha256=PRIOR_SHA,
          source_pins=pins, library_sha256=previous["library_sha256"], saved_control_sha256=SAVED_SHA, conditioning_bytes=0))
    if not fully_resident(before):
        return
    (root/"tmp").mkdir()
    (root/"fonts").mkdir()
    for font in (PRIOR/"fonts").glob("fontlist-*.json"):
        (root/"fonts"/font.name).write_bytes(font.read_bytes())
    env = environment(root)
    env.update(TMPDIR=str(root/"tmp"), XDG_CACHE_HOME=str(root/"tmp"))
    argv = command(root, timed["command"])
    write(root/"preflight.json", receiver_preflight(root, argv, env, capabilities=(FLAG, "--prove-no-active-curvature")))
    measure_mode(root, "candidate", argv, env, resident, require_success=False)
    write(root/"prediction-seal.json", seal(root))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    launch(cli.parse_args().root)
