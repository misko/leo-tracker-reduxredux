"""Observe the deployed screened nomination without paying another fit."""

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch


VARIANTS = Path("/opt/leo-algo08/algo08v3/payload/tools/pipeline_eval/variants")
SCREEN_PIN = "f276b8ee2f4c059d571da874b2fbef6f6b13d08078e30fd93950428f8c10fb70"
CORE_PIN = "30e6f22ab4b49d03cf8536645cbdebb8fec2afa513f3cfa4a9f3163590a84407"
NOMINATION_PIN = "89dbecd98b182562830623c93b96e05f3880b9b791cd8bc87ec66e618ccb5a11"


def assignments(node):
    rows = node["seed"]["rows"]
    result = [(str(row["component"]),int(row["candidate_index"]),int(row["candidate_norad"]),int(alias))
              for row,alias in zip(rows,node["aliases"],strict=True)]
    if len(result)!=len({row[0] for row in result}):
        raise ValueError("Named screened nomination returned duplicate components")
    return sorted(result)


def observe(screen, emit):
    def wrapped(scan, nodes, metrics):
        before = [assignments(node) for node in nodes]
        result = screen(scan,nodes,metrics)
        selected,_ = result
        if len(selected["choices"])!=1:
            raise ValueError("Expected the original installed selected hypothesis")
        winner, = selected["choices"]
        gate = winner["arms"]["c0"]["metrics"]
        winning = assignments(winner["node"])
        if winning not in before or len(metrics["screen_c0_scores"])!=len(before):
            raise ValueError("Installed screen chose a node outside its paid rank list")
        if metrics["winning_rank"] is not None and before[metrics["winning_rank"]]!=winning:
            raise ValueError("Installed score ordering and selected signature disagree")
        tracks = {}
        for track in scan.tracks:
            key = track["key"]
            if key in tracks:
                raise ValueError("Installed scan has duplicate components")
            tracks[key] = tuple(str(oid) for oid in track["observation_ids"])
        eligible = {row[0] for node in before for row in node}
        if not eligible <= tracks.keys():
            raise ValueError("Named finalists do not bind the original Graph")
        masks = []
        for row in gate["tracks"]:
            key = row["component"]
            if len(tracks[key])!=row["points"]:
                raise ValueError("Named initial gate changed the bound track span")
            masks.append(dict(component=key,norad=int(row["norad"]),compatible=bool(row["compatible"]),
                              points=int(row["points"]),aliases_changed=int(row["aliases_changed"])))
        emit(dict(signatures=before, scores=list(metrics["screen_c0_scores"]),winning_rank=metrics["winning_rank"],
                  winning_assignment=winning, fallback=bool(metrics["fallback"]),
                  completed_c0_score=metrics["completed_c0_score"], gate=masks,
                  observations={key:tracks[key] for key in sorted(eligible)}))
        return result
    return wrapped


@contextmanager
def binding(emit):
    from tools.pipeline_eval.variants import algo08_stock_finish, v5_core, v5_screen_winner

    expected = [(algo08_stock_finish,"algo08_stock_finish.py",NOMINATION_PIN),
                (v5_core,"v5_core.py",CORE_PIN),(v5_screen_winner,"v5_screen_winner.py",SCREEN_PIN)]
    for module,name,digest in expected:
        file = VARIANTS/name
        if Path(module.__file__).resolve()!=file or sha256(file.read_bytes()).hexdigest()!=digest:
            raise ValueError("Installed named nomination source differs")
    original = v5_screen_winner.screen_nodes
    if Path(original.__code__.co_filename).resolve()!=VARIANTS/"v5_screen_winner.py":
        raise ValueError("Installed screen was already replaced")
    emitted = False

    def collect(row):
        nonlocal emitted
        if emitted:
            raise ValueError("An additional installed cold screen reached the scoped trace")
        emitted = True
        emit(row)

    with patch.object(v5_screen_winner,"screen_nodes",observe(original,collect)):
        yield
