"""Prepare only the frozen rank-four DS30 input for the pending comparison."""

import argparse
from pathlib import Path
import sys

CASE = "DS30-0163"
RANK_HASH = "0f748653d7f68d810e1ac6f1136a41386ef5e92195f9a225f0e91955c0ec9222"
PAIR_PIN = "d9d80afa50d537d34500288972114312af7137c93cc173f147bef800ea8d7442"
INPUTS = dict(
    native_sha256="f026bb3822ad7a946979a091c55b06d11d7c675e667c564f7d984e9f38fb2651",
    inventory_sha256="d30888ead13433a1194dec7286e2a71af3d4d78876733eadd8becc06c7121ddd",
    offer_sha256="2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236",
    terminal_sha256="sha256:b9d9469933acde146fafa6af859f1d6d28b27b883ffb00f39d7cbe7872a896f7",
    archive_sha256="sha256:811cfbf510db5a7cccbcc32cc8102616f5e225a91c3924f64596ce22ee7bc687",
    frozen_specification="sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f",
    cutoff_utc_ns=1794785574519046150,
    issued=6772, admitted=5330, probes=10660, factors=3731,
)


def assigned():
    from reports.ALGO08.v3.nomination_handoff_0419_admission import enrollment

    assignment = enrollment(ranked=4, case=CASE, ranking_hash=RANK_HASH, pair_pin=PAIR_PIN)
    return assignment | {"order": assignment["planned_order"], "archived_pair_sha256": PAIR_PIN}


def prepare(root):
    from reports.ALGO08.v3 import nomination_handoff_0419_local as shared

    shared.launch(root, assign=assigned, execute=False, expected_inputs=INPUTS)


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ready_root", type=Path)
    prepare(parser.parse_args().ready_root)
