"""Read sealed detector pairs and replay only their released Graph preparations."""

import argparse
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import fmean

from signed_cfo_time import ALIAS, ARMS, SAMPLE_RATE, blocks, dependence, difference, split, winner


HERE = Path(__file__).resolve().parent
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124/cases")
WEAK = Path("/dev/shm/leo-v3-integrated-original-02/DS30-0016")
WEAK_STOCK = Path("/dev/shm/leo-v3-stock-raw-repeat-DS30-0016-01/stock")
SPARSE = "c5b57b0602e81a6a85c14caf648eb12341f098d09915b4d3f705094ed309574c"
FULL = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
CASES = {"DS30-0049": 2, "DS30-0274": 1, "DS30-0019": 1, "DS30-0016": None}
PINS = {
    "assets/tracks.json": "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a",
    "src/leo/analysis/localization_v3/tracks.py": "db44a947666c2dd7946534f69bf6af72ced63c8af553bb1b089c0fba3d5b7b6f",
    "src/leo/analysis/graph_tracklets.py": "74575f44c4e9716707faaac56e3e7c35bb423ba0f75332656d7c6576cd8f2c27",
    "src/leo/analysis/glrt_frequency_input.py": "e7ad53bf41c596042c654184c8f212f4ec187c9281d4944725344d7f5e3ee58b",
}


def tag(data):
    return "sha256:"+sha256(data).hexdigest()


def canonical(value):
    return tag(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode())


def document(path, expected=None):
    data = path.read_bytes()
    if expected is not None and tag(data) != "sha256:"+expected.removeprefix("sha256:"):
        raise ValueError(f"Sealed input differs at {path}")
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def read_native(folder, expected):
    path, = (folder/"fast-scan-automatic-work").glob("*/detections.json")
    native = document(path, expected)
    view, book = native["source"], native["provenance"]
    if (view["sample_rate_hz"] != SAMPLE_RATE or view["analysis_manifest_sha256"]
            != canonical(["cancellation", view["raw_recording_authority_digest"], book["detector_sha256"][7:], view["probes"]])):
        raise ValueError("Native authenticated digest or hardware rate changed")
    return native


def campaign(case, role):
    root = CAMPAIGN/case/role/f"attempt-{CASES[case]:06d}"
    result = document(root/"result.json")
    if (result["outcome"] != "complete" or result["algorithm"] != role or result["process"]["exit_code"]
            or result["generation"] != CASES[case]):
        raise ValueError("Unqualified original receiver input")
    return root/"publication", result


def candidate(case):
    if CASES[case] is None:
        folder = WEAK/"candidate"
        signed = document(HERE/"measurements/integrated-original.json.gz",
                          "eb115ec1dd7a734693e21d8be49e2f7de87fe48936b8db8d51e1216cf37a0dff")
        result = signed["runs"]["positive_first"][case]["result"]["document"]
        raw = result["receiver"]
        input_sha = raw["native_sha256"]
        offer = raw["requested_offer_sha256"]
    else:
        folder, result = campaign(case, "successor")
        raw = document(folder/"unified-short-bootstrap.json")
        input_sha = result["native_sha256"]
        offer = result["raw_identity"]["region_sha256"]
    return qualified_candidate(folder, raw, input_sha, offer)


def qualified_candidate(folder, raw, input_sha, offer):
    """Bind a selected publication to the frozen unfiltered 20/8 native recipe."""
    witness = document(folder/"exact-named-raw-witness.json")
    held = raw["held_anchor_route"]
    native = read_native(folder, input_sha)
    parent = {key: val for key, val in held["receiver_recipe"].items() if key != "held_native_8ms"}
    probes = native["source"]["probes"]
    source = native["source"]
    digest = canonical(["cancellation", source["raw_recording_authority_digest"], canonical(parent)[7:], probes])
    base = dict(native, source=dict(source, analysis_manifest_sha256=digest),
                provenance=dict(native["provenance"], detector_sha256=canonical(parent), run_id="blind-compact-"+digest[7:39]))
    if (held["choice"]["route"] != "unfiltered" or held["refinement_calls"]
            or canonical(base) != held["parent_native_sha256"] or canonical(parent) != held["parent_detector_sha256"]
            or held["selected"] != held["observed"] or held["selected"] != sum(len(row["candidates"]) for row in probes)
            or parent["aperture_samples"] != [200_000,80_000] or parent["shortened_sha256"] != SPARSE
            or parent["installed_sha256"] != FULL or held["native_sha256"] != input_sha
            or witness["evidence"]["detail"]["input_sha256"] != input_sha
            or raw["requested_offer_sha256"].removeprefix("sha256:") != offer.removeprefix("sha256:")):
        raise ValueError("Sparse rows or original supplied offer are no longer the enrolled packet")
    return native, witness, offer


def installed(case, offered):
    if CASES[case] is None:
        q = document(HERE/"measurements/stock-raw-repeat-0016.json.gz",
                     "e852ffcf8b887e7cab66bcb5f8ad4911caaaa9398264d3b5f351b02862b17850")
        stock = q["stock"]
        folder, expected, science = WEAK_STOCK, stock["digest"], stock["science"]
        offer = q["admission"]["request"]["offer_sha256"]
        raw = document(Path("/var/tmp/leo-full-short-DS30-0016-pair/stock/joint-research-receipt.json"),
                       "f6c56736b6382ca1c8fc062d49e5e2d9503230a3c6d82ede33cf607e5fe81bed")
        ordered = raw["selected_rows"]
        if raw["receipt"]["terminal_sha256"] != science["receipt"]["terminal_sha256"]:
            raise ValueError("Installed weak owners refer to a different terminal")
    else:
        folder, result = campaign(case, "installed")
        expected, science, offer = result["native_sha256"], result["evidence"], result["raw_identity"]["region_sha256"]
        ordered = None
        if case == "DS30-0049":
            q = document(Path("/tmp/leo-v3-0049-saved-cross-proof02/installed-installed/crossover-worker.json"),
                         "86d3b27db6e1bb85f69e180228ff6b7b977d4779f1b42c018ce054475c2c3141")
            if (q["submitted_native_sha256"] != expected
                    or q["receipt"]["terminal_sha256"] != science["receipt"]["terminal_sha256"]):
                raise ValueError("Installed development owners refer to a different input or terminal")
            ordered = q["ordered_owners"]
    native = read_native(folder, expected)
    if offered.removeprefix("sha256:") != offer.removeprefix("sha256:") or native["provenance"]["detector_sha256"] != "sha256:"+FULL:
        raise ValueError("Installed region or native receiver changed")
    return native, None if ordered is None else owners(ordered, science["owners"])


def owners(ordered, digests):
    result = {}
    for arm in ARMS:
        rows = ordered[arm]
        ids = {i:n for i,n,r in rows}
        if len(ids) != len(rows) or canonical(ids) != digests[arm]:
            raise ValueError("Published ordered owners do not reproduce their official digest")
        result[arm] = {i:(n,r) for i,n,r in rows}
    return result


def opportunities(native):
    session = native["source"]["session_id"]
    schedule, result = Counter(), {}
    rows = native["source"]["probes"]
    for left,right in zip(rows[::2],rows[1::2],strict=True):
        key = tuple(left[k] for k in ("edge","channel","actual_rf_hz"))
        index = schedule[key]
        schedule[key] += 1
        for radio,row in enumerate((left,right)):
            t = row["valid_start_counter"]
            if row["receiver_id"] != radio or any(left[k]!=row[k] for k in (
                "edge","channel","actual_rf_hz","valid_start_counter","visit_index"
            )):
                raise ValueError("Original stereo visit identity changed")
            identity = tag(f'{session}:{radio}:{t}'.encode())
            if identity in result:
                raise ValueError("Duplicate original opportunity")
            result[identity] = dict(id=identity, row=row, counter=t, short=index % 8 != 0,
                                    lane_index=index, radio=radio, factor=winner(row))
    return result


def graph(native, opp):
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from numpy.polynomial.legendre import legval

    config = document(RELEASE/"assets/tracks.json", PINS["assets/tracks.json"])["config"]
    packet = prepare_tracks(native, TrackConfig(**config))
    membership, pieces, ambiguous = {}, {}, set()
    curved = set(packet["curved_indices"])
    for j,track in enumerate(packet["tracks"]):
        ids = dict(zip(sorted(track["indices"]), zip(track["observation_ids"],track["times"],track["values"],strict=True),
                       strict=True))
        if len(ids) != len(track["observation_ids"]):
            raise ValueError("Graph track membership changed")
        for i,piece in enumerate(track["pieces"]):
            identifier = track["key"], i
            present = []
            for ordinal,index in enumerate(sorted(piece["indices"])):
                owner,t,value = ids[index]
                item = opp[owner]
                frequency = item["factor"]["fractional_tracking_cfo_hz"]
                d = (float(value)-frequency)/ALIAS
                lift = round(d)
                if abs(d-lift)>1e-8:
                    raise ValueError("Graph value ceased to be the original signed CFO plus an integer alias")
                trend = float(legval((t-piece["reference_time_s"])/piece["time_scale_s"],piece["coefficients_hz"]))
                row = dict(item, track=track["key"], piece=identifier, ordinal=ordinal, lift=lift,
                           graph_residual_hz=float(value)-trend, curved=j in curved)
                if owner in membership:
                    ambiguous.add(owner)
                membership[owner] = row
                present.append(row)
            pieces[identifier] = present
    valid_pieces = {key: rows for key,rows in pieces.items() if not any(row["id"] in ambiguous for row in rows)}
    good = {row["id"]:row for rows in valid_pieces.values() for row in rows}
    return good, valid_pieces, dict(tracks=len(packet["tracks"]), assigned=packet["graph_points"],
                                   curved_tracks=len(curved), ambiguous_piece_rows=len(ambiguous))


def bind_pair(stock, sparse, left, right):
    for field in ("session_id","input_manifest_sha256","raw_recording_authority_digest","capture_start_utc_ns"):
        if stock["source"][field] != sparse["source"][field]:
            raise ValueError("Paired raw authority changed")
    if (any(stock[k] != sparse[k] for k in ("clock_anchor","delivery_clocks","last_sample_counter"))
            or stock["provenance"]["excluded_windows"] != sparse["provenance"]["excluded_windows"]
            or list(left) != list(right)):
        raise ValueError("Paired original chronology or exclusion changed")
    if any({k:v for k,v in left[oid]["row"].items() if k!="candidates"}
           != {k:v for k,v in right[oid]["row"].items() if k!="candidates"} for oid in left):
        raise ValueError("Paired original RF, channel or sample opportunity changed")


def compare(left, right, lg, rg, owner_sets):
    pairs, ctr, deltas, anchors = [], Counter(), [], []
    for oid,a in left.items():
        b = right[oid]
        label = "short" if b["short"] else "full_anchor"
        ctr[label+"_opportunities"] += 1
        if a["factor"] is None or b["factor"] is None:
            ctr[label+("_installed_only" if a["factor"] else "_sparse_only" if b["factor"] else "_both_empty")] += 1
            continue
        ctr[label+"_both_positive"] += 1
        delta, shift, close, wrap = difference(a["factor"], b["factor"])
        ctr[label+"_wrapped_close"] += wrap
        if label == "full_anchor":
            ctr["full_anchor_exact_factor"] += a["factor"] == b["factor"]
            anchors.append(delta)
        if not close:
            continue
        ctr[label+"_same_atom"] += 1
        if label == "short":
            deltas.append(delta)
        if oid in lg and oid in rg:
            x,y = lg[oid],rg[oid]
            pairs.append(dict(installed=x,candidate=y,delta_hz=delta,epoch_delta=shift,
                              relative_lift=y["lift"]-x["lift"], installed_residual=x["graph_residual_hz"],
                              candidate_residual=y["graph_residual_hz"]))
            ctr[label+"_both_graph_pieces"] += 1
    groups = defaultdict(list)
    for match in pairs:
        groups[(match["candidate"]["piece"],match["installed"]["piece"])].append(match)
    runs = [r for group in groups.values() for r in split(group)]
    metrics = {key: dependence(runs,key) for key in ("delta_hz","installed_residual","candidate_residual")}
    metrics["per_radio"] = {str(radio):dependence([r for r in runs if r[0]["candidate"]["radio"]==radio],"delta_hz")
                            for radio in (0,1)}
    old,new = owner_sets
    owned = {}
    for arm in ARMS:
        eligible = set(new[arm]) if old is None else {key for key,val in new[arm].items() if old[arm].get(key)==val}
        selected = [piece for run in runs for piece in split(row for row in run if row["candidate"]["id"] in eligible)]
        owned[arm] = dict(scope="published candidate map only" if old is None else "identical published owner and role in both",
                          matched_graph_rows=sum(map(len,selected)), dependence=dependence(selected,"delta_hz"))
    return dict(opportunities=ctr, matched_short_delta_mean_hz=fmean(deltas) if deltas else None,
                matched_short_delta_rms_hz=fmean(d*d for d in deltas)**.5 if deltas else None,
                full_anchor_delta_range_hz=[min(anchors),max(anchors)] if anchors else None,
                paired_runs=len(runs), metrics=metrics, owners=owned,
                actual_calibrated_per_point_residuals=None)


def run(plan_path):
    from leo.analysis import graph_tracklets, glrt_frequency_input
    from leo.analysis.localization_v3 import tracks
    for module in (graph_tracklets,glrt_frequency_input,tracks):
        source = Path(module.__file__).resolve()
        if tag(source.read_bytes())[7:] != PINS[str(source.relative_to(RELEASE))]:
            raise ValueError("Unexpected released Graph code")
    current, exposure = {}, {}
    for case in CASES:
        native,witness,offer = candidate(case)
        opp = opportunities(native)
        assigned,pieces,scope = graph(native,opp)
        archived = witness["ports"]["graph"]["graph"]
        if any(scope[k]!=archived[k] for k in ("assigned","tracks")):
            raise ValueError("Pinned Graph replay disagrees with the archived candidate roster")
        choices = [(key, blocks(rows),len(rows),rows[0]["curved"]) for key,rows in pieces.items()]
        exposure[case] = dict(accepted_candidate_sha256=canonical(native),scope=scope,
                              curved_points=sum(n for _,p,n,curved in choices if curved),
                              curved_block_count=sum(len(b) for _,b,n,curved in choices if curved),
                              proposed_pairs=[dict(piece=key,rows=pair,curved=curved) for key,B,n,curved in choices for pair in B])
        current[case] = native,witness,offer,opp,assigned
    plan = dict(protocol_sha256=tag((HERE/"signed-cfo-time-protocol.md").read_bytes()),candidate_only=exposure)
    encoded = json.dumps(plan,sort_keys=True,indent=2,allow_nan=False)+"\n"
    if plan_path.exists():
        if plan_path.read_text() != encoded:
            raise ValueError("The frozen candidate-only block plan changed")
    else:
        with plan_path.open("x") as target:
            target.write(encoded)
    result = {}
    for case,(native,witness,offer,opp,assigned) in current.items():
        stock, stock_owners = installed(case,offer)
        other = opportunities(stock)
        bind_pair(stock,native,other,opp)
        prior,_,other_scope = graph(stock,other)
        evidence = witness["evidence"]
        own = owners(evidence["owner_rows"],evidence["owner_maps"])
        if any(not set(v)<=opp.keys() for v in own.values()):
            raise ValueError("Published owner lacks an original opportunity")
        info = compare(other,opp,prior,assigned,(stock_owners,own))
        info.update(installed_sha256=canonical(stock), installed_graph=other_scope, candidate=exposure[case]["scope"],
                    candidate_blocking={k:v for k,v in exposure[case].items() if k!="proposed_pairs"},
                    rank_cpu_ns=[r["cpu_ns"] for r in witness["ports"]["rank"]])
        result[case] = info
    return dict(plan_sha256=tag(encoded.encode()), geometry_solves=0, waveform_reads=0, cases=result)


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("candidate_plan", type=Path)
    args=cli.parse_args()
    print(json.dumps(run(args.candidate_plan),sort_keys=True,indent=2,allow_nan=False))
