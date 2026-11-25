from pathlib import Path

from reports.ALGO08.v3 import directed_insertion_0049_position as check


def test_only_prepared_native_and_explicit_causal_data_mount_read_only():
    catalogue = Path("/dev/shm/source/orbit.tle")
    args = check.command(([catalogue],(Path("/usr"),)),smoke=False)
    pairs = [tuple(args[i+1:i+3]) for i,value in enumerate(args) if value=="--ro-bind"]
    assert (str(catalogue),str(catalogue)) in pairs
    for name in ("plan.json","derived-native.json"):
        path = str(check.ROOT/name)
        assert (path,path) in pairs
    assert "/srv/bulk" not in args and args[-1] == "paid-child"
    assert args[:3] == ["/usr/bin/taskset","-c","2"]


def test_proof_uses_cpu3_and_has_no_paid_entry():
    args = check.command(([],()),smoke=True)
    assert args[:3] == ["/usr/bin/taskset","-c","3"]
    assert args[-1] == "smoke-child"
    assert check.TIMEOUT==15.
