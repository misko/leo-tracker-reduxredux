"""Count state stability within frames separately from changes between frames."""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from extend import OUT, sha, write  # noqa: E402


def main():
    counts = defaultdict(Counter)
    windows = defaultdict(Counter)
    transitions = []
    sources = {}
    census = json.loads((OUT / "census.json").read_text())
    for c in census["captures"]:
        p = OUT / "decoded" / c["unit"] / "windows.json"
        sources[str(p)] = sha(p)
        rows = json.loads(p.read_text())["rows"]
        for row in rows:
            frame_states = defaultdict(list)
            for w in row["windows"]:
                key = f"{w['first_symbol']}-{w['last_symbol']}"
                windows[c["dataset"]][key + ":tested"] += 1
                windows[c["dataset"]][key + ":accepted"] += w["accepted"]
                if w["known_phase"] is not None:
                    frame_states[w["frame"]].append(w["known_phase"])
            consistent = {}
            for f, phases in frame_states.items():
                if len(phases) >= 2:
                    counts[c["dataset"]]["multiwindow_frames"] += 1
                    counts[c["dataset"]]["multiwindow_single_state"] += len(set(phases)) == 1
                if len(set(phases)) == 1:
                    consistent[f] = phases[0]
            if len(consistent) == 2:
                phases = list(consistent.values())
                changed = phases[0] != phases[1]
                counts[c["dataset"]]["two_frame_tracks"] += 1
                counts[c["dataset"]]["two_frame_state_changed"] += changed
                transitions.append(dict(id=f"{c['unit']}-T{row['index']:04d}",
                                        frame_states=consistent, changed=changed))
    write(OUT / "word-structure.json", dict(
        counts=dict(counts), windows=dict(windows), transitions=transitions,
        method_sha256=sha(Path(__file__)), source_sha256=sources,
        limitation="Accepted generator matches only; no claim about unaccepted windows. "
        "Tracks/frames/windows can be dependent. State changes are not payload bit changes.",
    ))
    print(json.dumps(dict(counts), indent=2))


if __name__ == "__main__":
    main()
