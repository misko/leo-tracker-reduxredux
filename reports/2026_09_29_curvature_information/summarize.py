import hashlib
import json

from study import HERE, ROOT


def main():
    data = json.loads((HERE / "results.json").read_text())
    for name, digest in data["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    assert len(data["panels"]) == 9 and all(p["qualified"] for p in data["panels"].values())
    lines = [
        "| Panel | Tracks | Shared slope retention | "
        "Shared curvature retention | Per-track curvature retention |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, p in data["panels"].items():
        r = p["results"]
        lines.append(
            f"| {name} | {p['cases']} | "
            f"{100 * r['slope']['full']['shared']['retention'][0]:.2f}% | "
            f"{100 * r['curvature']['full']['shared']['retention'][0]:.2f}% | "
            f"{100 * r['curvature']['full']['track']['retention'][0]:.2f}% |"
        )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 5))
    names = list(data["panels"])
    for offset, arm, label, color in (
        (-0.18, "slope", "Shared slope", "#ca7135"),
        (0.18, "curvature", "Shared curvature", "#246d9b"),
    ):
        values = [
            100 * data["panels"][n]["results"][arm]["full"]["shared"]["retention"][0] for n in names
        ]
        ax.barh([i + offset for i in range(9)], values, height=0.35, label=label, color=color)
    ax.set(
        yticks=range(9),
        yticklabels=[n.replace("_8", "").replace("_", " ") for n in names],
        xlim=(0, 100),
        xlabel="Minimum generalized position-information retention (%)",
        title="Curvature preserves more position information than slope\n"
        "Same 1,732 tracks; scan timing profiled out",
    )
    ax.invert_yaxis()
    ax.legend()
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(HERE / "retention.png", dpi=170)


if __name__ == "__main__":
    main()
