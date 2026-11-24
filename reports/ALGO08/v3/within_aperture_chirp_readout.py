"""Read sealed original packet pairs and grade the post-centroid chirp envelope."""

from collections import Counter
from math import remainder, sqrt
from pathlib import Path
from statistics import fmean
import json

from signed_cfo_time import ALIAS, difference
from signed_cfo_time_readout import (
    CAMPAIGN, FULL, PINS, RELEASE, SPARSE, bind_pair, canonical, document, opportunities, read_native, tag,
)
from within_aperture_chirp import BIN_HZ, SLOPE_STRESS, bounds, compare_bounds, exposure


CASES = ("DS30-0220","DS30-0274")
SOURCE_PINS = {
    "/tmp/leo-v3-short-rank-transfer-DS30-0016-01/sparse/timing_first_receiver.c":
        "10d8ec75ac2d6e820dd9cee184b2825b8d6510a465bbb8bfa38fc782126daea5",
    "/var/tmp/leo-v3-eight-ms-build-padded/8ms/two_carrier_receiver.c":
        "6f21e36a55caa489f5992a3fbae6006c2af549c30753b7053fae926d0cefb48e",
    "/var/tmp/leo-v3-eight-ms-build-padded/scouts/8ms/portable_verifier.c":
        "bae3798db85b2682ae88d7ce545aac0d084c5f3a747d34cf5c43edd908e0996b",
    "/var/tmp/leo-v3-eight-ms-build-padded/scouts/8ms/delay_product_kernel.c":
        "d4f199ee7fe3d5208d15887054982206f659d58988c086439cff3b0e62e2bbf5",
    "/var/tmp/leo-short-signed-02/control/portable_verifier.c":
        "3f62918238ad9107474d2f1509e953c61776eb70123ecd880c514f6e6483a707",
    "/var/tmp/leo-short-signed-02/control/delay_product_kernel.c":
        "d014fe0670ff7a926bbd302ada1f4d021fe2f488f91b32dae8b4fe1634a07f1c",
}


def paired(case):
    branches = {}
    for role in ("installed","successor"):
        folder = CAMPAIGN/case/role/"attempt-000001"
        result = document(folder/"result.json")
        publication = folder/"publication"
        native = read_native(publication,result["native_sha256"])
        if (result["process"]["exit_code"] or result["generation"]!=1 or result["outcome"]!="complete"
                or result["algorithm"]!=role):
            raise ValueError("Original field pair did not complete")
        branches[role] = native,result,publication
    full,a,_ = branches["installed"]
    sparse,b,folder = branches["successor"]
    raw = document(folder/"unified-short-bootstrap.json")
    held = raw["held_anchor_route"]
    recipe = held["receiver_recipe"]
    base_recipe = {k:v for k,v in recipe.items() if k!="held_native_8ms"}
    source = sparse["source"]
    p = sparse["provenance"]
    detector = canonical(base_recipe)
    before = canonical(["cancellation",source["raw_recording_authority_digest"],detector[7:],source["probes"]])
    base = dict(sparse,source=dict(source,analysis_manifest_sha256=before),
                provenance=dict(p,detector_sha256=detector,run_id="blind-compact-"+before[7:39]))
    if (a["raw_identity"]!=b["raw_identity"] or a["authority_sha256"]!=b["authority_sha256"]
            or b["raw_identity"]["window_count"]<6000
            or full["provenance"]["detector_sha256"]!="sha256:"+FULL or held["choice"]["route"]!="unfiltered"
            or held["refinement_calls"] or held["native_sha256"]!=b["native_sha256"]
            or held["observed"]!=held["selected"]
            or held["selected"]!=sum(len(row["candidates"]) for row in source["probes"])
            or canonical(base)!=held["parent_native_sha256"] or detector!=held["parent_detector_sha256"]
            or canonical(recipe)!=p["detector_sha256"] or base_recipe["shortened_sha256"]!=SPARSE
            or base_recipe["installed_sha256"]!=FULL or base_recipe["aperture_samples"]!=[200_000,80_000]):
        raise ValueError("Input pairing, authority or verifier aperture differs")
    old,new=opportunities(full),opportunities(sparse)
    bind_pair(full,sparse,old,new)
    scope={key:a["raw_identity"][key] for key in ("raw_authority_sha256","inventory_sha256","region_sha256",
                                                  "archive_sha256","causal_cutoff_utc_ns","window_count")}
    scope["leases"] = {role: record["lease_id"] for role, (_, record, _) in branches.items()}
    return full,old,new,raw["receiver_audit"]["native"],scope,[a["native_sha256"],b["native_sha256"]]


def original_pieces(native):
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from numpy.polynomial.legendre import Legendre

    prepared = prepare_tracks(native,TrackConfig(**document(RELEASE/"assets/tracks.json",PINS["assets/tracks.json"])["config"]))
    rows,duplicates = {},set()
    for track in prepared["tracks"]:
        indices = dict(zip(sorted(track["indices"]),zip(track["observation_ids"],track["times"],strict=True),strict=True))
        for piece in track["pieces"]:
            p = Legendre(piece["coefficients_hz"])
            slopes,cuv = p.deriv(),p.deriv(2)
            turn = [float(x.real) for x in cuv.deriv().roots() if x.imag==0]
            info=(piece["start_s"],piece["end_s"],piece["reference_time_s"],piece["time_scale_s"],slopes,cuv,turn)
            for k in piece["indices"]:
                identity,t=indices[k]
                if identity in rows:
                    duplicates.add(identity)
                rows[identity]=t,info
    return {k:v for k,v in rows.items() if k not in duplicates},dict(tracks=len(prepared["tracks"]),
        assigned=prepared["graph_points"],ambiguous_piece_points=len(duplicates))


def local_rates(item, full, short):
    t,(start,stop,ref,scale,d1,d2,turn)=item
    lower,upper=min(full.extent[0],short.extent[0]),max(full.extent[1],short.extent[1])
    first,last=t-.01+lower,t-.01+upper
    if first < start or last > stop:
        return None
    lo,hi=(first-ref)/scale,(last-ref)/scale
    extrema=[lo,hi,*[x for x in turn if lo < x < hi]]
    a=float(d1((t-.01+full.centroid-ref)/scale))/scale
    b=max(abs(float(d2(x))) for x in extrema)/(scale*scale)
    return a,b


def summary(values):
    if not values:
        return None
    ordered=sorted(values)
    return dict(n=len(values),mean=fmean(values),rms=sqrt(fmean(v*v for v in values)),
                p50=ordered[(len(values)-1)//2],p95=ordered[int(.95*(len(values)-1))],maximum=ordered[-1])


def readout(case):
    native,stock,sparse,clocks,scope,pins=paired(case)
    pieces,graph_info=original_pieces(native)
    counts=Counter()
    quantities: dict[str,list[float]]={}
    evidence=[]
    for key,v in stock.items():
        w=sparse[key]
        a,b=v["factor"],w["factor"]
        slot="short" if w["short"] else "anchor"
        counts[slot+"_attempts"]+=1
        if a is None or b is None:
            counts[slot+("_installed_only" if a else "_sparse_only" if b else "_both_empty")]+=1
            continue
        counts[slot+"_both_positive"]+=1
        delta,offset,match,wrap=difference(a,b)
        if not w["short"]:
            counts["anchor_exact"]+=a==b
            continue
        counts["short_same_atom"]+=match
        counts["short_wrapped_only"]+=wrap and not match
        counts["short_different_epoch"]+=abs(offset)>2.
        for threshold in (BIN_HZ,1000,10000,100000):
            label=int(round(threshold))
            counts[f"short_abs_signed_gt_{label}"]+=abs(delta)>threshold
            counts[f"short_abs_alias_folded_gt_{label}"]+=abs(remainder(delta,ALIAS))>threshold
        if not match:
            continue
        first,second=exposure(a,False),exposure(b,True)
        counts[f"frame_support_{len(first.centres)}_and_{len(second.centres)}"]+=1
        if key not in pieces:
            counts["short_same_atom_no_original_piece"]+=1
            continue
        rate=local_rates(pieces[key],first,second)
        if rate is None:
            counts["short_same_atom_piece_edge"]+=1
            continue
        slope,curvature=rate
        if abs(slope)>SLOPE_STRESS:
            counts["short_above_stress_slope"]+=1
            continue
        bnd=compare_bounds(first,second,slope,curvature)
        values=dict(signed_delta_hz=delta,centroid_diagnostic_adjusted_delta_hz=delta-bnd["centroid_term_hz"],
                    estimated_signed_slope_hz_per_s=slope,estimated_absolute_slope_hz_per_s=abs(slope),
                    modeled_max_absolute_curvature_hz_per_s2=curvature,
                    uniform_short_power_bound=bnd["candidate"]["uniform_power_bound"],
                    uniform_full_power_bound=bnd["installed"]["uniform_power_bound"],
                    short_phase_arc_rad=bnd["candidate"]["max_frame_phase_arc_rad"],
                    full_phase_arc_rad=bnd["installed"]["max_frame_phase_arc_rad"],
                    short_delay_spread_rad=bnd["candidate"]["delay_product_phase_spread_rad"],
                    full_delay_spread_rad=bnd["installed"]["delay_product_phase_spread_rad"],
                    short_margin=b["fractional_margin"],full_margin=a["fractional_margin"],
                    **{k:x for k,x in bnd.items() if isinstance(x,float)})
        for k,x in values.items():
            quantities.setdefault(k,[]).append(x)
        counts["estimated_central_lobe_only_support_below_error"]+=(
            bnd["centered_carrier_support_bound_hz"]<abs(values["centroid_diagnostic_adjusted_delta_hz"]))
        evidence.append([key,v["radio"],v["row"]["channel"],v["counter"],len(first.centres),len(second.centres),values])
    native_times = {k:dict(calls=n,cpu_ns=clocks["native_cpu_ns"][k],
                           mean_cpu_ns=clocks["native_cpu_ns"][k]/n)
                    for k,n in clocks["native_calls"].items()}
    return dict(scope=scope,native_sha256=pins,installed_graph=graph_info,counts=counts,
                moments={k:summary(v) for k,v in quantities.items()},native_exclusive=native_times,
                matched_local_rows_sha256=canonical(evidence))


def run():
    from leo.analysis import graph_tracklets,glrt_frequency_input
    from leo.analysis.localization_v3 import tracks
    for name,want in SOURCE_PINS.items():
        if tag(Path(name).read_bytes())[7:]!=want:
            raise ValueError("Original scout or verifier code changed")
    for module in (graph_tracklets,glrt_frequency_input,tracks):
        source=Path(module.__file__).resolve()
        if tag(source.read_bytes())[7:]!=PINS[str(source.relative_to(RELEASE))]:
            raise ValueError("Original Graph preparation changed")
    factor=dict(integer_epoch_sample=20,fractional_epoch_offset_samples=.5)
    stress={label:bounds(exposure(factor,short),SLOPE_STRESS) for label,short in (("full",False),("short",True))}
    return dict(asymptotic_bin_hz=BIN_HZ,stress_slope_hz_per_s=SLOPE_STRESS,stress=stress,
                sources=SOURCE_PINS,graph_source_pins=PINS,cases={case:readout(case) for case in CASES},
                waveform_reads=0,solver_fits=0,benchmarks=0)


if __name__=="__main__":
    print(json.dumps(run(),sort_keys=True,indent=2,allow_nan=False))
