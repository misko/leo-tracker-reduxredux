"""Run the owner-blind discrete replay and then join its frozen result to owners."""

from hashlib import sha256
from pathlib import Path
import argparse
import gzip
import json

from pre_screen_owner import Curve, prepare, score


HERE = Path(__file__).resolve().parent
ROOT = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124/cases")
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
SOURCES = {
    "assets/tracks.json": "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a",
    "src/leo/analysis/localization_v3/tracks.py": "db44a947666c2dd7946534f69bf6af72ced63c8af553bb1b089c0fba3d5b7b6f",
    "src/leo/analysis/graph_tracklets.py": "74575f44c4e9716707faaac56e3e7c35bb423ba0f75332656d7c6576cd8f2c27",
    "src/leo/analysis/glrt_frequency_input.py": "e7ad53bf41c596042c654184c8f212f4ec187c9281d4944725344d7f5e3ee58b",
}
CASES = {
    "DS30-0220": dict(native="868ee4137fbac20bc917ea2b3128bb26ff36cd3ffb2a4d6f81fb7e164b0ef6a5",
                    charted="b8be7fef63a425d3fd15de1ca206f6ec40be65b96afa8d114fb0e8808c8a36eb",
                    crossover="cbc1ae11c9a40f9d667bd45966d3dffc40b6c3b8d94a15fcdf9cbe38018a2455"),
    "DS30-0086": dict(native="3a5063c98f0b3223c170712dd9fd7b8df8ff6dce45f2c78e21a55483d2b8885d",
                    charted="5d775bbb9ff01ca9943c8001ed316cd2d65925da8348368452ddd8c0855ae084",
                    crossover="e98fac35839b13c3b002cc1ba53ce50111cb53f86e6bb735ca1985c1b89a6da9"),
}
ARMS = ("c0","fitted_c")


def signature(value):
    return "sha256:" + sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def checked(path, pin):
    body = path.read_bytes()
    if sha256(body).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Arms or original source changed at {path}")
    return body


def document(path,pin):
    body = checked(path,pin)
    return json.loads(gzip.decompress(body) if path.suffix==".gz" else body)


def make_curves(native):
    from leo.analysis.localization_v3 import tracks
    from leo.analysis import glrt_frequency_input, graph_tracklets
    from leo.analysis.polynomial_tracklets import TrackConfig

    for module in (tracks,glrt_frequency_input,graph_tracklets):
        file = Path(module.__file__).resolve()
        checked(file,SOURCES[str(file.relative_to(RELEASE))])
    path = RELEASE/"assets/tracks.json"
    config = TrackConfig(**document(path,SOURCES["assets/tracks.json"])["config"])
    graph = tracks.prepare_tracks(native,config)
    curves = {
        row["key"]:Curve(row["receiver"],row["channel"],row["rf_hz"],
                         tuple(row["observation_ids"]))
        for row in graph["tracks"]
    }
    count = sum(len(c.observations) for c in curves.values())
    if (len(curves)!=len(graph["tracks"]) or count!=graph["graph_points"]
            or count!=len({oid for c in curves.values() for oid in c.observations})):
        raise ValueError("Released Graph did not reproduce unique signed opportunity membership")
    return curves


def inputs(case, pins):
    root = ROOT/case/"successor/attempt-000001/publication"
    native_path, = (root/"fast-scan-automatic-work").glob("*/detections.json")
    native = document(native_path,pins["native"])
    witness = document(root/"exact-named-raw-witness.json",pins["charted"])
    if witness["evidence"]["detail"]["input_sha256"] != "sha256:"+pins["native"]:
        raise ValueError("Archived charted branch was priced on a different native packet")
    curves = make_curves(native)
    return witness,native,curves,prepare(curves,witness["ports"]["history_risk"])


def owner_map(rows, digest):
    result = {oid:(norad,role) for oid,norad,role in rows}
    if (len(result)!=len(rows) or signature({oid:n for oid,(n,_) in result.items()})!=digest
            or any(r not in ("conditional","predictive") for _,r in result.values())):
        raise ValueError("Actual ordered owner rows do not reproduce the published map")
    return result


def owner_grade(case,pins, inputs):
    witness,native,curves,replay = inputs
    tail = case.removeprefix("DS30-")
    cross = document(HERE/"measurements"/f"field-receiver-solver-cross-{tail}.json.gz",pins["crossover"])
    score_old, admission = cross["score"], cross["admission"]
    if (cross["clock"]["exit_code"] or admission["native_sha256"]!="sha256:"+pins["native"]
            or cross["worker"]["verified_handoffs"]!=1 or admission["waveform_reads"]
            or admission["archive_sha256"]!=witness["solver_recipe"]["archive_sha256"]
            or score_old["named_mixed"]["region"]!=witness["evidence"]["detail"]["region"]
            or score_old["new_owners"]!=cross["worker"]["ordered_owners"]
            or admission["original_raw"]!=native["source"]["raw_recording_authority_digest"]):
        raise ValueError("Installed owners are not qualified on the charted native packet and offer")
    arms = {}
    saved = witness["evidence"]
    for arm in ARMS:
        old = owner_map(score_old["new_owners"][arm],score_old["new_owner_maps"][arm])
        current = owner_map(saved["owner_rows"][arm],saved["owner_maps"][arm])
        grade = score(replay,curves,old,current)
        if any(value for key,value in grade["repaired_publication_parity"].items() if key!="shared"):
            raise ValueError(f"Repaired curve reconstruction differs from charted {arm} publication")
        arms[arm] = grade
    return dict(arms=arms, stage_sizes={label:len(rows) for label,rows in replay["stages"].items()},
                graph_components=len(curves),clocks=replay["clocks"],signed_status=replay["signed_status"],
                no_install_cold_signatures_in_archive=True)


def run(frozen):
    cases = {case:inputs(case,pins) for case,pins in CASES.items()}
    nominations = {key:case[3]["nominee"] for key,case in cases.items()}
    freeze_body = json.dumps(dict(cases=CASES,nominations=nominations),sort_keys=True,indent=2)+"\n"
    with frozen.open("x") as out:
        out.write(freeze_body)
    return dict(cases=CASES,nominations=nominations,source_sha256=SOURCES,
                pre_owner_sha256=sha256(freeze_body.encode()).hexdigest(),
                judged={key:owner_grade(key,CASES[key],case) for key,case in cases.items()},
                waveform_reads=0,solver_workers=0,location_fits=0,gps_reads=0)


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("freeze_file",type=Path)
    print(json.dumps(run(parser.parse_args().freeze_file),indent=2,sort_keys=True,allow_nan=False))
