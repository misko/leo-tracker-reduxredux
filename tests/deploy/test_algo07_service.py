from pathlib import Path


def test_algo07_template_requires_install_time_release_and_activation_cutoff():
    root = Path(__file__).parents[2]
    unit = (root / "deploy/systemd/leo-algo07-graph-position.service").read_text()
    assert "WorkingDirectory=@RELEASE@" in unit
    assert "-m leo.cli.fast_graph_position_v6" in unit
    assert "--minimum-completed-utc-ns @CUTOFF_UTC_NS@" in unit
    assert "--maximum-seconds 1200" in unit
    assert "fast-scan-graph-position-v6" in unit
    assert "After=local-fs.target leo-algo06-graph-position.service" in unit
    assert "InaccessiblePaths=/mnt/qnap01" in unit
    assert "KillMode=control-group" in unit
    assert "OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1" in unit
