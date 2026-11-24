"""Run the assigned 0086 holdout only after the frozen 0049 challenge passes."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sparse8_cfo_epoch_trial import HERE, MODES, document, run, score


CASE = "DS30-0086"
PAIR = "407765fa47754cc99556143888b286e88f4674ab21836d3f437ac8af4c2ca439"
ADMISSION = "0edbc20d3e2c5ef90a1a324a4f92da72cfe9105c89dc68cba74235815f4aec2b"
PROTOCOL = HERE / "sparse8-cfo-epoch-transfer-protocol.md"
CHALLENGE = Path("/dev/shm/leo-v3-cfo-epoch-0049-saved01")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path)
    parser.add_argument("--challenge-score", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", choices=MODES)
    group.add_argument("--score")
    args = parser.parse_args()
    challenge = document(CHALLENGE / "score.json", args.challenge_score)
    if challenge["case"] != "DS30-0049" or challenge["stop"]:
        raise ValueError("The development challenge failed the frozen transfer gate")
    admission = document(args.stage / "admission.json", ADMISSION)
    if args.score:
        score(args.stage, args.score, case=CASE, protocol=PROTOCOL, native_pin=admission["native_pin"],
              pair_pin=PAIR, require_grid_parity=True)
    else:
        run(args.stage, args.run, admission=ADMISSION, case=CASE, protocol=PROTOCOL)
