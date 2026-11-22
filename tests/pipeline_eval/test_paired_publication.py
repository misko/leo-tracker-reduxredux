import json
from types import SimpleNamespace

import pytest

from tools.pipeline_eval.qualification import paired_publication as bench


@pytest.mark.parametrize("mismatch", [False, True])
def test_pair_uses_empty_outputs_and_only_credits_same_recording(tmp_path, monkeypatch, mismatch):
    args = SimpleNamespace(cpu=2, first="candidate", recording=tmp_path/"recording",
                           region=tmp_path/"region", output=tmp_path/"results",
                           baseline="baseline", candidate="candidate")
    calls = []

    def measure(launcher, root, _args):
        assert not root.exists()
        root.mkdir()
        calls.append(launcher)
        return dict(elapsed_s=4 if launcher=="baseline" else 2,
                    raw_authority=launcher if mismatch else "same",
                    receipt=dict(session_id="s", region={"width_km":25}, window_count=4))

    monkeypatch.setattr(bench, "measure", measure)
    monkeypatch.setattr(bench, "LOCK", tmp_path/"test.lock")
    monkeypatch.setattr(bench.os, "sched_getaffinity", lambda _: {2})
    monkeypatch.setattr(bench.os, "sched_setaffinity", lambda *args: None)
    monkeypatch.setattr(bench.os, "setpriority", lambda *args: None)
    monkeypatch.setattr(bench.subprocess, "run", lambda *args, **kwargs: None)
    if mismatch:
        with pytest.raises(ValueError, match="different waveform"):
            bench.run_pair(args)
    else:
        bench.run_pair(args)
    report=json.loads((args.output/"pair.json").read_bytes())
    assert calls == ["candidate", "baseline"]
    if mismatch:
        assert "failure" in report and "elapsed_ratio" not in report
    else:
        assert report["elapsed_ratio"] == 0.5
    with pytest.raises(FileExistsError):
        bench.run_pair(args)


def test_verified_withholding_counts_as_a_terminal_publication(tmp_path):
    scans=bench.FastScanStore(tmp_path)
    publications=bench.FastStandardAnalysisStore(tmp_path)
    rid="algo08-v2-trial"
    region=dict(center=[-32.0,95.0], width_km=25.0, screen_center=[-32.0,95.0])
    arms={a: {"latlon":None} for a in ("c0","fitted_c")}
    terminal=dict(reason="no probes", arms=arms)
    digest=bench.canonical_digest(terminal)
    bench.immutable_json(scans.automatic_workspace(rid)/"terminal.json",terminal)
    scans.publish(rid,dict(session_id="s", points=[]))
    publications.withhold(rid,terminal["reason"],terminal_sha256=digest,region=region,raw_authority="raw")
    receipt=dict(run_id=rid,session_id="s",region=region,decision="withheld",terminal_sha256=digest)
    result=bench.evidence(tmp_path,receipt,0)
    assert result["arms"]==arms and result["reason"]=="no probes" and result["artifacts"]==[]
