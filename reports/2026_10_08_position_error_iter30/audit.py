"""Archive-only coverage/finalist diagnosis; reference used only for audit distances."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.regional_position_score import coordinates  # noqa: E402
from leo.contracts.regional_position import RegionalPrior  # noqa: E402

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_10_08_position_error_iter29"


def distance(prior, point, document):
    lat, lon = np.radians(coordinates(prior, point))
    rlat, rlon = np.radians(
        [document["reference_latitude_deg"], document["reference_longitude_deg"]]
    )
    h = np.sin((lat - rlat) / 2) ** 2 + np.cos(lat) * np.cos(rlat) * np.sin((lon - rlon) / 2) ** 2
    return float(2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(h, 0, 1))))


def reference_xy(prior, document):
    lat0, lon0 = np.radians([prior.latitude_deg, prior.longitude_deg])
    lat, lon = np.radians([document["reference_latitude_deg"], document["reference_longitude_deg"]])
    bearing = np.arctan2(
        np.sin(lon - lon0) * np.cos(lat),
        np.cos(lat0) * np.sin(lat) - np.sin(lat0) * np.cos(lat) * np.cos(lon - lon0),
    )
    d = distance(prior, [0, 0], document)
    result = np.array([d * np.sin(bearing), d * np.cos(bearing)])
    np.testing.assert_allclose(coordinates(prior, result), np.degrees([lat, lon]), atol=1e-8)
    return result


def main():
    cases, hashes = {}, {}
    fig, axes = plt.subplots(2, 2, figsize=(13, 10), layout="constrained")
    for ax, label in zip(axes.flat, [f"RESERVED-{i:03d}" for i in range(1, 5)], strict=True):
        documents = {}
        for kind in ("baselines", "regions"):
            path = PREVIOUS / kind / f"{label}.json"
            hashes[str(path.relative_to(HERE.parent))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            documents[kind] = json.loads(path.read_text())
        d = documents["baselines"]
        prior = RegionalPrior(
            latitude_deg=d["prior_latitude_deg"],
            longitude_deg=d["prior_longitude_deg"],
            radius_km=d["prior_radius_km"],
        )
        ref = reference_xy(prior, d)
        points = []
        for row in d["methods"][0]["points"]:
            xy = [row["east_km"], row["north_km"]]
            points.append(dict(**row, reference_error_km=distance(prior, xy, d)))
        scored = sorted(
            [r for r in points if r["objective"] is not None], key=lambda r: r["objective"]
        )
        for rank, row in enumerate(scored, 1):
            row["score_rank_all_scored"] = rank
        converged = [r for r in scored if r["converged"]]
        for rank, row in enumerate(converged, 1):
            row["score_rank_converged"] = rank
        nearest = min(points, key=lambda r: r["reference_error_km"])
        regional = {}
        for kind, document in documents.items():
            assert [
                (r["east_km"], r["north_km"], r["spacing_km"])
                for r in document["methods"][0]["points"]
            ] == [(r["east_km"], r["north_km"], r["spacing_km"]) for r in points]
            basins = [
                dict(**r, reference_error_km=distance(prior, [r["east_km"], r["north_km"]], d))
                for r in document["diagnostics"]["retained_basins"]
            ]
            finals = []
            for r in document["diagnostics"]["final_starts"]:
                if r["fit"] is None:
                    continue
                fit = r["fit"]
                finals.append(
                    dict(
                        arm=r["arm"],
                        basin=r["basin"],
                        start=r["start"],
                        converged=fit["converged"],
                        objective=fit["objective"],
                        point=fit["vector"][:2],
                        reference_error_km=distance(prior, fit["vector"][:2], d),
                    )
                )
            regional[kind] = dict(basins=basins, finals=finals)
        cases[label] = dict(
            reference_point_km=ref.tolist(),
            grid_count=len(points),
            nearest_point=nearest,
            best_coarse_point=scored[0],
            nearest_by_spacing={
                str(s): min(
                    [r for r in points if r["spacing_km"] == s],
                    key=lambda r: r["reference_error_km"],
                )
                for s in sorted({r["spacing_km"] for r in points})
            },
            points=points,
            regional=regional,
            best_within_radius={
                str(radius): next((r for r in scored if r["reference_error_km"] <= radius), None)
                for radius in (5, 10, 25)
            },
        )
        xy = np.array([[r["east_km"], r["north_km"]] for r in scored]) - ref
        scatter = ax.scatter(
            xy[:, 0],
            xy[:, 1],
            c=np.arange(1, len(scored) + 1),
            cmap="viridis_r",
            s=18,
            alpha=0.7,
            label="Evaluated coarse points",
        )
        basins = (
            np.array([[r["east_km"], r["north_km"]] for r in regional["baselines"]["basins"]]) - ref
        )
        ax.scatter(
            basins[:, 0],
            basins[:, 1],
            marker="s",
            s=100,
            facecolors="none",
            edgecolors="red",
            label="Ordinary finalists",
        )
        extras = (
            np.array([[r["east_km"], r["north_km"]] for r in regional["regions"]["basins"]]) - ref
        )
        ax.scatter(
            extras[:, 0], extras[:, 1], marker="+", s=110, color="orange", label="Sep25 finalists"
        )
        ax.scatter([0], [0], marker="*", s=150, color="black", label="Reference, audit only")
        ax.set(
            title=label,
            xlabel="East of reference (km)",
            ylabel="North of reference (km)",
            aspect="equal",
        )
        ax.legend(fontsize=7)
        ax.grid(alpha=0.2)
        fig.colorbar(scatter, ax=ax, label="Coarse score rank (1 = lowest)", shrink=0.8)
        print(
            label,
            "nearest",
            nearest["reference_error_km"],
            "rank",
            nearest.get("score_rank_all_scored"),
            "basins",
            [r["reference_error_km"] for r in regional["baselines"]["basins"]],
        )
    output = dict(
        scope="Post-hoc archive-only audit; no new localization fits or operational reference seed",
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        input_sha256=hashes,
        cases=cases,
    )
    (HERE / "audit.json").write_text(json.dumps(output, indent=2) + "\n")
    fig.savefig(HERE / "coverage-and-finalists.png", dpi=160)


if __name__ == "__main__":
    main()
