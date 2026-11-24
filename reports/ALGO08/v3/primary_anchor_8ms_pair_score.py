"""Compare verified North raw exits for the two 20/8 ms anchor policies."""

import argparse
from pathlib import Path
from unittest.mock import patch

from combined_raw_trial import source_at
from continued_cfo_first_0016 import read, write
import eight_ms_native_score as native_score
from eight_ms_native_score import same_images
from primary_anchor_8ms_trial import pin, score, verify
from prospective_0316_solver import owner_delta


def with_common_options(command):
    normalized = list(command)
    for flag in ("--output","--full-anchor-primary-library"):
        if flag in normalized:
            i = normalized.index(flag)
            del normalized[i:i+2]
    return normalized


def pair(root):
    candidate, control = root/"primary-anchor", root/"full-anchor"
    launch = [read(p/"binding.json") for p in (candidate,control)]
    left,right = launch
    if (with_common_options(left["command"]) != with_common_options(right["command"])
            or "--full-anchor-primary-library" not in left["command"] or "--full-anchor-primary-library" in right["command"]
            or any(left[field]!=right[field] for field in ("source_sha256","request","libraries","machine","commit"))):
        raise ValueError("The North pair differs beyond its 20 ms anchor policy")
    if not (candidate/"seal.json").exists():
        verify(candidate)
    if not (candidate/"score.json").exists():
        score(candidate)
    if not (control/"science-seal.json").exists():
        ordinary = native_score.checked

        def frozen_runtime(path, sha):
            if path.name == "primary_anchor_8ms_trial.py" and sha == right["source_sha256"][path.name]:
                source_at(right["commit"],path.name,sha)
                return None
            return ordinary(path,sha)

        with patch.object(native_score,"checked",frozen_runtime):
            native_score.north_seal(control)
    left,right = read(candidate/"seal.json"),read(control/"science-seal.json")
    after,before = left["science"],right["science"]
    def clocks(run):
        raw = run["raw"]
        acquisition = raw["receiver_audit"]
        return dict(exit=run["clock"], authenticated=acquisition["acquire"], native=acquisition["native"],
                    phases=raw["phases"], numerical=run["solve"])
    write(root/"result.json",dict(order=read(root/"pair.json")["order"],
         candidate=clocks(left),control=clocks(right),candidate_score=read(candidate/"score.json"),
         historical=left["old_clock"], changed_anchors=left["changed_anchors"],
         native_sha256={"primary":left["raw"]["native_sha256"],"full":right["raw"]["native_sha256"]},
         early=dict(candidate=left["graph"],control=right["early"]),
         exact_selected_and_outputs=None if after is None else dict(arms=after["arms"]==before["arms"],
             owners=after["roles"]==before["roles"],grid_and_path=after["grid_and_path"]==before["grid_and_path"],
             pngs=same_images(after["images"],before["images"])),
         owners=None if after is None else {arm:owner_delta(before["roles"][arm],after["roles"][arm]) for arm in before["roles"]},
         comparison_sha256={"primary":pin(candidate/"seal.json"),"full":pin(control/"science-seal.json")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root",type=Path)
    pair(parser.parse_args().root)
