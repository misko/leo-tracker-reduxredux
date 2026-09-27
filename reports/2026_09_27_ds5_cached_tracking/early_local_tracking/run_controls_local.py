"""Use the fixed control protocol with a separate candidate and output directory."""
import json
from engine_local import HERE, create
import run_controls as original


def run():
    # Pin the adapter and candidate alongside all inherited scientific sources.
    parent = json.loads((HERE.parent / 'early_confirmed_tracking/source_lock.json').read_text())['files']
    assert all(original.study.digest(p) == h for p, h in parent.items())
    write = original.write
    def checked_write(path, value):
        assert all(original.study.digest(p) == h for p, h in parent.items())
        if path.name == 'source_lock.json':
            value['files'].update(parent)
        write(path, value)
    original.HERE = HERE
    original.create = create
    original.write = checked_write
    original.run()


if __name__ == '__main__':
    run()
