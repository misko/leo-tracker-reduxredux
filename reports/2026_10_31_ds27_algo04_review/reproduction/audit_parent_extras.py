"""Render parent-span top-ten sources absent the primary contiguous top ten; no fit."""

import argparse
import copy
import gzip
import io
import json
from pathlib import Path

import audit_top_fragments as audit
from rank_native_residuals import digest, export_plot_packet, polynomial, published_owners, read_bound, runs


def parent_rows(inventory, contexts):
    primary = {(r["case"], r["track_index"]) for r in inventory["tracks"][:10]}
    rows = []
    for parent in inventory["parent_tracks"][:10]:
        key = parent["case"], parent["track_index"]
        if key in primary:
            continue
        row = copy.deepcopy(next(r for r in inventory["tracks"] if (r["case"], r["track_index"]) == key))
        track = contexts[parent["case"]]["tracks"][parent["track_index"]]
        selected = set(parent["remaining_observation_ids"])
        ix = [i for i, oid in enumerate(track["observation_ids"]) if oid in selected]
        assert set(track["observation_ids"][i] for i in ix) == selected
        row.update(rank=parent["parent_rank"], fragment_id=parent["track_id"] + "-parent-span",
                   observation_ids=[track["observation_ids"][i] for i in ix], source_local_indices=ix,
                   points=parent["points"], start_s=min(track["times"][i] for i in ix),
                   end_s=max(track["times"][i] for i in ix), duration_s=parent["duration_s"],
                   max_gap_s=parent["max_gap_s"], parent_view=True,
                   contiguous_fragments=parent["contiguous_fragments"],
                   longest_native_fragment_duration_s=parent["longest_native_fragment_duration_s"],
                   source_piece_index=0 if len(track.get("pieces", [])) == 1 else None,
                   view_definition="Remaining native parent first-to-last span; gaps retained, not a contiguous-duration claim")
        rows.append(row)
    return rows


def render(output, rows, contexts, records):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output.mkdir(parents=True, exist_ok=True)
    by_rank = {r["rank"]: r for r in records}
    for row in rows:
        context = contexts[row["case"]]
        track = context["tracks"][row["track_index"]]
        lookup = {o["observation_id"]: o for o in context["observations"]}
        focus = set(row["observation_ids"])
        fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, layout="constrained")
        lane = [o for o in context["observations"] if (o["receiver"], o["channel"]) == (row["receiver"], row["channel"]) and row["start_s"]-5 <= o["time_s"] <= row["end_s"]+5]
        for label, color, chosen in (("Published associated", ".7", [o for o in lane if o["observation_id"] in context["associated"]]),
                                     ("Other unpublished GLRT", "darkorange", [o for o in lane if o["observation_id"] not in context["associated"] | focus]),
                                     ("Remaining native parent", "crimson", [lookup[oid] for oid in row["observation_ids"]])):
            axes[0].scatter([o["time_s"] for o in chosen], [o["measured_cfo_hz"]/1000 for o in chosen], s=16, c=color, label=label)
        gap_runs = runs(track, set(track["observation_ids"])-focus)
        for n, ix in enumerate(gap_runs):
            if row["source_piece_index"] is None:
                continue
            times = [track["times"][i] for i in ix]
            pred = [polynomial(track["pieces"][0], t) for t in times]
            axes[0].plot(times, [(v-(track["values"][i]-lookup[track["observation_ids"][i]]["measured_cfo_hz"]))/1000 for i,v in zip(ix,pred,strict=True)], c="tab:blue", label="Existing native polynomial (broken at >5s gaps)" if n==0 else None)
            axes[1].plot(times, [track["values"][i]-v for i,v in zip(ix,pred,strict=True)], ".-", c="crimson")
        axes[0].set(ylabel="Native CFO (kHz)")
        axes[1].set(xlabel="Native scan time (s)", ylabel="Point minus existing polynomial (Hz)")
        axes[1].axhline(0,c=".5",lw=.7)
        for ax in axes: ax.grid(alpha=.2)
        axes[0].legend(fontsize=8)
        fig.suptitle(f"Parent rank {row['rank']}: {row['case']} RX{row['receiver']} CH{row['channel']} {row['points']} points\nParent span {row['duration_s']:.3f}s; max gap {row['max_gap_s']:.3f}s; longest contiguous piece {row['longest_native_fragment_duration_s']:.3f}s — gaps retained")
        fig.savefig(output/f"parent-{row['rank']:02}-{row['case']}-native.png",dpi=145)
        plt.close(fig)
        for version,evidence in by_rank[row["rank"]]["versions"].items():
            folds = [f for a in evidence["annotations"] if a["annotation"] and not a["source_match"]["disjoint_from_ranked_fragment"] for f in a["annotation"]["folds"] if f.get("retained_held_residual_mapping")=="exact_native_order_and_recorded_groups"]
            seeds = sorted({f["seed"] for f in folds})
            if not seeds: continue
            fig,axes=plt.subplots(len(seeds),1,figsize=(12,2.5*len(seeds)),squeeze=False,layout="constrained")
            for ax,seed in zip(axes.flat,seeds,strict=True):
                for f in folds:
                    if f["seed"]!=seed:continue
                    points=[(t,v) for t,v,use in zip(f["held_times_s"],f["held_residual_hz"],f["held_ranked_fragment_mask"],strict=True) if use]
                    ax.plot([p[0] for p in points],[p[1] for p in points],".",label=f"{f['arm']} NORAD {f['norad_hypothesis']} hypothesis; alias {f['alias']}")
                ax.axhline(0,c=".5",lw=.7);ax.grid(alpha=.2);ax.legend(fontsize=8);ax.set(title=f"Saved whole-group seed {seed}",ylabel="Held residual (Hz)")
            axes.flat[-1].set(xlabel="Native scan time (s)")
            fig.suptitle(f"Parent rank {row['rank']}: {row['case']} {version}, stored held residuals\n{row['duration_s']:.3f}s parent span with {row['max_gap_s']:.3f}s maximum gap; no continuous-duration or confirmed-identity claim")
            fig.savefig(output/f"parent-{row['rank']:02}-{row['case']}-{version}-held.png",dpi=145)
            plt.close(fig)


def main(index_path, inventory_path, output):
    output.mkdir(parents=True,exist_ok=False)
    hashes={str(Path(__file__).resolve()):digest(__file__)}
    index=read_bound(index_path,hashes=hashes);inventory=read_bound(inventory_path,hashes=hashes)
    contexts={}
    for parent in inventory["parent_tracks"][:10]:
        case=parent["case"]
        if case in contexts:continue
        entry=next(e for e in index["cases"] if e["case"]==case)
        terminal=read_bound(entry["terminal_path"],entry["terminal_sha256"],hashes)
        contexts[case]=dict(tracks=read_bound(entry["tracks_path"],entry["tracks_sha256"],hashes),observations=read_bound(entry["observations_path"],entry["observations_sha256"],hashes),associated=set(published_owners(terminal)))
    rows=parent_rows(inventory,contexts)
    path=output/"parent-extra-rows.json";path.write_text(json.dumps(rows,indent=2)+"\n")
    report=audit.run(index_path,path,output/"annotation",plots=False)
    export_plot_packet(output/"native-inputs.json.gz",rows,contexts,{})
    native=json.loads(gzip.decompress((output/"native-inputs.json.gz").read_bytes()))
    diagnostic=json.loads(gzip.decompress((output/"annotation/annotation-plot-inputs.json.gz").read_bytes()))
    packet=dict(schema="ds27-parent-extra-plot-packet/v1",native=native,diagnostic=diagnostic)
    stream=io.BytesIO()
    with gzip.GzipFile(fileobj=stream,mode="wb",filename="",mtime=0) as archive:archive.write(json.dumps(packet,sort_keys=True,separators=(",",":")).encode())
    (output/"parent-plot-inputs.json.gz").write_bytes(stream.getvalue())
    render(output,rows,contexts,report["tracks"])
    (output/"input-source-sha256.json").write_text(json.dumps(hashes,indent=2)+"\n")


def replay(packet_path,output):
    p=json.loads(gzip.decompress(packet_path.read_bytes()))
    assert p["schema"]=="ds27-parent-extra-plot-packet/v1"
    contexts={case:dict(tracks=c["tracks"],observations=c["observations"],associated=set(c["associated_ids"])) for case,c in p["native"]["cases"].items()}
    render(output,p["native"]["top10"],contexts,p["diagnostic"]["tracks"])


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--index",type=Path);p.add_argument("--inventory",type=Path);p.add_argument("--packet",type=Path);p.add_argument("--output",required=True,type=Path);a=p.parse_args()
    if a.packet:replay(a.packet,a.output)
    else:main(a.index,a.inventory,a.output)
