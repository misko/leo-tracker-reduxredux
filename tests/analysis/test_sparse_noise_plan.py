import json

from tools.diagnose_sparse_noise import prepare


def test_noise_controls_preserve_frozen_membership_and_use_no_fitted_scale(tmp_path):
    source = tmp_path / "source.json"
    original = {
        "job_id": "original",
        "model": "formal-orbit-correction-v6",
        "model_config": {},
        "config": {},
        "numerical_source_hash": "old",
        "subset": {
            "method": "density",
            "seed": 0,
            "fraction": 1 / 32,
            "fitting_ids": ["a", "b"],
            "evaluation_ids": ["held"],
        },
    }
    source.write_text(json.dumps({"jobs": [original], "manifest_hash": "frozen"}))
    output = tmp_path / "result.json"
    prepare(source, output)
    jobs = json.loads(output.read_text())["jobs"]
    assert len(jobs) == 3
    assert len({j["job_id"] for j in jobs}) == 3
    assert all(j["subset"] == original["subset"] for j in jobs)
    assert all("measurement_sigma_hz" not in j["model_config"] for j in jobs)
    assert all("truth" not in j for j in jobs)
