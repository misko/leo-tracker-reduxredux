"""Independent Cholesky Schur audit and finite-profile qualification replay."""

import math

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from study import HERE, ROOT, read, save, verify  # noqa: E402


def main():
    plan = read(HERE / "plan.json")
    bindings = read(HERE / "input-seal.json")["sha256"]
    rows = []
    for unit in plan["units"]:
        folder = HERE / "runs" / unit["unit_id"]
        assert read(folder / "exit.json")["exit_code"] == 0
        for n, h in read(folder / "seal.json")["sha256"].items():
            assert n not in bindings or bindings[n] == h
            bindings[n] = h
        r = read(folder / "result.json")
        assert r["center"] == unit["x"]
        center = np.asarray(r["center"])
        node_distance = abs(center[2:] * 4 - np.round(center[2:] * 4)) / 4
        np.testing.assert_array_equal(
            r["steps"], np.r_[[0.002, 0.002], np.minimum(0.0001, node_distance / 2)]
        )
        old = read(ROOT / unit["baseline_held"])
        assert abs(r["center_score"] - old["training_log_score"]) < 1e-7
        assert abs(r["center_held_score"] - old["held_log_score"]) < 1e-7
        for m in r.get("matrices", []):
            raw = np.asarray(m["raw"])
            h = np.asarray(m["symmetric"])
            np.testing.assert_allclose(h, (raw + raw.T) / 2, rtol=0, atol=1e-12)
            assert (
                abs(
                    m["asymmetry"] - np.linalg.norm(raw - raw.T) / max(np.linalg.norm(raw.T), 1e-15)
                )
                < 1e-12
            )
            if "spatial" in m:
                factor = np.linalg.cholesky(h[2:, 2:])
                b = np.linalg.solve(factor, h[2:, :2])
                spatial = h[:2, :2] - b.T @ b
                np.testing.assert_allclose(spatial, m["spatial"], rtol=1e-8, atol=1e-6)
                np.testing.assert_allclose(
                    np.linalg.eigvalsh(spatial), m["eigenvalues"], rtol=1e-8, atol=1e-6
                )
        profiles = r["profiles"]
        if r["curvature_qualified"]:
            assert len(profiles) == 8
            assert all(m["asymmetry"] <= 0.01 and min(m["eigenvalues"]) > 0 for m in r["matrices"])
            assert r["profile_relative_change"] <= 0.01
            fine = r["matrices"][1]
            a, b = (np.asarray(m["spatial"]) for m in r["matrices"])
            assert (
                abs(
                    r["profile_relative_change"]
                    - np.linalg.norm(a - b) / max(np.linalg.norm(b), 1e-15)
                )
                < 1e-12
            )
            np.testing.assert_allclose(
                r["one_nat_distances_km"], np.sqrt(2 / np.asarray(fine["eigenvalues"]))
            )
            for p in profiles:
                offset = p["sign"] * p["radius_km"] * np.asarray(fine["eigenvectors"])[:, p["axis"]]
                np.testing.assert_allclose(p["position"], center[:2] + offset, rtol=0, atol=1e-12)
                assert (
                    abs(
                        p["quadratic_loss"]
                        - 0.5 * p["radius_km"] ** 2 * fine["eigenvalues"][p["axis"]]
                    )
                    < 1e-10
                )
                eligible = []
                for start in p["starts"]:
                    assert start["boundary"] == bool(
                        np.any(5 - abs(np.asarray(start["timing"])) < 0.001)
                    )
                    passed = (
                        start["success"]
                        and not start["boundary"]
                        and max(map(abs, start["gradient"])) <= 0.01
                    )
                    assert passed == start["qualified"]
                    if passed:
                        eligible.append(start)
                if "selected" not in p:
                    assert p["reason"] == "position_outside_domain"
                    continue
                chosen = max(eligible, key=lambda s: s["score"]) if eligible else None
                assert chosen == p["selected"]
                if chosen:
                    checks = p["checks"]
                    assert len(checks) == 2 * len(chosen["timing"])
                    assert [c["step"] for c in checks] == [0.0000625, 0.00003125] * len(
                        chosen["timing"]
                    )
                    assert p["step_agreement"] == [
                        abs(checks[2 * i]["numerical"] - checks[2 * i + 1]["numerical"])
                        for i in range(len(chosen["timing"]))
                    ]
                    for c in checks:
                        i = c["axis"] - 2
                        assert c["difference"] == abs(c["numerical"] - p["timing_gradient"][i])
                        t, step = chosen["timing"][i], c["step"]
                        assert c["crosses_node"] == (
                            math.floor((t - step) * 4) != math.floor((t + step) * 4)
                        )
                    passed = (
                        all(c["difference"] < 0.002 and not c["crosses_node"] for c in checks)
                        and max(p["step_agreement"]) < 0.002
                    )
                    assert passed == p["qualified"]
                    assert abs(r["center_score"] - p["score"] - p["training_loss"]) < 1e-8
        valid = [p for p in profiles if p["qualified"]]
        one = [p for p in valid if p["radius_km"] == 1]
        rows.append(
            dict(
                unit_id=unit["unit_id"],
                curvature_qualified=r["curvature_qualified"],
                one_nat_m=[1000 * v for v in r.get("one_nat_distances_km", [])],
                profiles_qualified=len(valid),
                profiles_total=len(profiles),
                one_km_min_loss=min((p["training_loss"] for p in one), default=None),
                one_km_max_loss=max((p["training_loss"] for p in one), default=None),
                held_better=sum(p["held_delta"] > 0 for p in valid),
                visible_changes=sum(p["visibility_changed"] for p in valid),
            )
        )
    verify(bindings)
    save(HERE / "summary.json", dict(audit_passed=True, rows=rows))
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), layout="constrained", sharex=True)
    x = np.arange(len(rows))
    for i, label in ((0, "Weak spatial direction"), (1, "Strong spatial direction")):
        axes[0].plot(
            x, [r["one_nat_m"][i] if r["one_nat_m"] else np.nan for r in rows], "o-", label=label
        )
    axes[0].axhline(1000, color="grey", linestyle=":")
    axes[0].set_ylabel("Local one-nat distance (m)")
    axes[0].legend()
    axes[1].plot(x, [r["one_km_min_loss"] for r in rows], "o-", label="Minimum audited loss")
    axes[1].plot(x, [r["one_km_max_loss"] for r in rows], "o-", label="Maximum audited loss")
    axes[1].set_ylabel("Training loss at 1 km (nats)")
    axes[1].legend()
    axes[1].set_xticks(x, [r["unit_id"].replace("_", " ") for r in rows], rotation=65, ha="right")
    fig.suptitle("Spatial likelihood shape after timing adjustment — not calibrated uncertainty")
    for suffix in ("png", "svg"):
        fig.savefig(HERE / ("profiles." + suffix), dpi=160)
    plt.close(fig)
    print(rows)


if __name__ == "__main__":
    main()
