import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from study import HERE, read  # noqa: E402

data = read(HERE / "summary.json")
assert data["complete"]
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
for i, ds in enumerate(("DS7", "DS8", "DS9")):
    rows = [r for r in data["scans"] if r["dataset"] == ds]
    axes[0].bar(
        i - 0.18,
        sum(r["track_sum"] for r in rows),
        width=0.35,
        color="#ca7135",
        label="Track fit" if i == 0 else None,
    )
    axes[0].bar(
        i + 0.18,
        sum(r["kl_delta"] for r in rows),
        width=0.35,
        color="#246d9b",
        label="Timing/component KL" if i == 0 else None,
    )
axes[0].set(
    xticks=range(3),
    xticklabels=["DS7", "DS8", "DS9"],
    ylabel="N24 − N8 mixture log-score contribution",
    title="Track fit accounts for the loss",
)
axes[0].legend(fontsize=8)
groups = [g for g in data["groups"] if g["group_by"] == ["receiver_id"]]
axes[1].bar(
    [f"RX{g['key'][0]}" for g in groups], [g["contribution"] for g in groups], color="#ca7135"
)
axes[1].set(title="Both receivers contribute", ylabel="Net track contribution (KL excluded)")
for ax in axes:
    ax.axhline(0, color="#333333", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
fig.suptitle("Posterior-dependent attribution; no tracks excluded or refitted")
fig.tight_layout()
fig.savefig(HERE / "attribution.png", dpi=170)
