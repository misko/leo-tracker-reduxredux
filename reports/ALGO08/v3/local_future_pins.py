"""Reviewed source digests of the local continuation and fixed-owner fit."""

from hashlib import sha256
from pathlib import Path

from aperture_trial import PAYLOAD, RELEASE


FILES = {
    "full_short_run.py": "8140600d5c3c86472ad0063ce077eeccfbc530b07a32f6c1bec154e33476430e",
    "joint_publication.py": "ddac992bb5c1046524b13505300f29dee9d19ab24136331825138dc882095d71",
    "blind_joint_route.py": "f7a66aea7ed875f5de067a0125948cd51c91e329ac0ea4b4ab1b4da6db5d1ca6",
    "blind_joint_finish.py": "7c2e710b7bc730e43c070057a1d40e26198febcdba423030555a7fd4531238f1",
    "local_future_inputs.py": "fa23f9c757bcf3be19cccfad77482621aa3b62720194b469bfd903e001ac44f3",
    "local_future_policy.py": "1b5268fc771ea327fda1216df5b4bba389c113caec7146b03c9f728c3d13ae84",
    "local_future_repair.py": "2c22d0badf4431e8ef7f914d1b65d80bfd96344dc8b9b52ed0c9687ee8150fbe",
    "causal_short_receiver.py": "61520e72ed4d1937319ae21f57e4e3f4bb566d14862a08a81f215dbfe0a5e0fe",
    "north_factor_swap.py": "2e974f0869f6edee312cd415fd61c16ee0a0caea2f9363f56ad43a84b8a65978",
    "payload/tools/algo08_position.py": "cd5c728e7f81b675b796d69713ca66e601a54534bdbf1d606dc8ecf16c4c138c",
    "payload/tools/pipeline_eval/variants/carrier_continuation.py": "f13fc2e02be5474de37b3efb5fba195e3a45daf534e3fa4e7d60c76500cef9ee",
    "release/src/leo/analysis/localization_v3/tracks.py": "db44a947666c2dd7946534f69bf6af72ced63c8af553bb1b089c0fba3d5b7b6f",
    "release/src/leo/analysis/localization_v3/event_position.py": "3a8c9bde7ddddc115fcb219f8588fd51188ef4081567d8e2fe91df8324418e9f",
    "release/src/leo/analysis/localization_v3/conservative_recovery.py": "9d5047f873a22790c4f0818877b09270ee91a0761a9a3d7204c8a849639ee656",
    "release/src/leo/analysis/localization_v3/history_policy.py": "429c230cb01438a4889f6e77256b7f00df4435b3522632bbef8cc2a83d223ca1",
    "release/src/leo/analysis/localization_v3/marginal.py": "c80ac51249578e8a2c6c6a13a04aaa22a168353b2c758155858106b91507b609",
    "release/src/leo/analysis/localization_v3/predictive_linear.py": "1c1930b8fc71b6fafd43fa744661a785b7d243b74b1ab39ab1f59d8fe800dcc6",
    "release/src/leo/analysis/research/retained_track_likelihood.py": "73c24d054d5676c7d7051779a6960f8f692ce0d97bc23d292470aa01f6110bcf",
}


def checked_dependencies():
    here = Path(__file__).resolve().parent
    for name, pin in FILES.items():
        domain, sep, path = name.partition("/")
        source = {"payload": PAYLOAD, "release": RELEASE}[domain] / path if sep else here / name
        if sha256(source.read_bytes()).hexdigest() != pin:
            raise ValueError(f"Unreviewed local repair dependency: {name}")
    return dict(FILES)
