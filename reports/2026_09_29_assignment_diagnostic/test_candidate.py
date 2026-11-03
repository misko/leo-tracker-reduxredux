import math
import unittest

import numpy as np
from scipy.special import logsumexp
from study import HERE, candidate_joint, prior, read

baseline, timing, model_class = prior.source.numerical_imports()
from trend_mixture import contrast_density  # noqa: E402


class CandidateTests(unittest.TestCase):
    def test_batched_candidate_probabilities_match_scalar_oracle(self):
        target = read(HERE / "manifest.json")["targets"][0]
        manifest = read(prior.SOURCE / "manifest.json")
        row = next(r for r in manifest["sets"] if r["unit"] == target["unit"])
        docs = baseline.load_documents(dict(config=manifest["config"], inputs=[row["input"]]))
        model = model_class(docs, manifest["config"], baseline.Stationary, 0.2)
        ti = next(i for i, t in enumerate(docs[0]["tracks"]) if t["track_id"] == target["track_id"])
        track = docs[0]["tracks"][ti]
        times = np.array([-5, -2.375, 0, 1.125, 5])
        for position in row["positions"][1:]:
            expected = []
            totals = []
            for t in times:
                prediction, visible = model.models[0].prediction(track, [*position, t])
                density, _ = contrast_density(track["y"][None, :] - prediction)
                joint = math.log(0.8) + np.where(visible, density, -np.inf) - math.log(sum(visible))
                total = np.logaddexp(logsumexp(joint), math.log(0.2) + model.background[0, ti][1])
                totals.append(total)
                expected.append(np.exp(joint - total))
            actual = candidate_joint(model.models[0], track, position, times, np.array(totals))
            np.testing.assert_allclose(actual, expected, rtol=1e-9, atol=1e-10)
            self.assertTrue(np.all(actual.sum(axis=1) <= 1 + 1e-10))


if __name__ == "__main__":
    unittest.main()
