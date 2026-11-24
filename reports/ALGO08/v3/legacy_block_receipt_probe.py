"""Compare late map-receipt serialization using existing JSON and empty scanner setup."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from legacy_block_setup_probe import measured, probe_roster


def primitive_write(path, payload):
    with path.open("x") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def child(mode, payload, output, entry, writer, argv):
    measured(entry, argv)
    from exact_named_raw import write

    body = json.loads(payload.read_bytes())
    names = set(sys.modules)
    started, cpu = perf_counter(), process_time()
    if mode == "scientific_default":
        write(output, body, scientific=True)
    else:
        sys.path.insert(0, str(writer.parent))
        from legacy_map_receipt import write as local

        local(output, body)
    codecs = dict(elapsed_s=perf_counter()-started, cpu_s=process_time()-cpu)
    print(json.dumps(dict(mode=mode, clock=codecs, additional_imports=sorted(set(sys.modules)-names),
                          receipt_sha256=sha256(output.read_bytes()).hexdigest())))


def compare(root, writer):
    sources = {"tiny": Path("/dev/shm/leo-v3-legacy-all-0107-result01/indexed/legacy-map-acquisition.json"),
               "positive": Path("/dev/shm/leo-v3-legacy-all-0016-result02/indexed/legacy-map-acquisition.json")}
    roster = probe_roster(root)
    python, isolation, _, entry, *argv = roster["all_member"]
    modes = ("scientific_default", "dedicated", "dedicated", "scientific_default")
    observations = []
    for case, source in sources.items():
        for count, mode in enumerate(modes):
            out = root/f"{case}-{count}.json"
            command = [python, isolation, __file__, "child", mode, str(source), str(out), entry, str(writer), *argv]
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=12)
            if result.returncode:
                raise ValueError(result.stderr)
            if out.read_bytes() != source.read_bytes():
                raise ValueError("The detached map receipt encoder changed byte custody")
            observations.append(json.loads(result.stdout) | {"case": case})
    primitive_write(root/"result.json", dict(runs=observations, unchanged_bytes=True, waveform_reads=0, solver_started=False,
          writer_path=str(writer), writer_sha256=sha256(writer.read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("compare", "child"))
    parser.add_argument("options", nargs=argparse.REMAINDER)
    choices = parser.parse_args()
    if choices.command == "compare":
        compare(Path(choices.options[0]), Path(choices.options[1]))
    else:
        mode, data, out, entry, writer, *argv = choices.options
        child(mode, Path(data), Path(out), Path(entry), Path(writer), argv)
