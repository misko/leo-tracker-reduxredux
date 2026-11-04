import json

import pytest

from leo.cli.algo07_profile import digest
from leo.storage.graph_terminal_reuse import TerminalReuse


class Source:
    def __init__(self, path):
        self.path = path
        self.calls = 0
        self.checks = 0
        self.valid_input = True
        path.write_text('{"state":"complete","nested":{"a":1}}')

    def verify_input(self, job):
        self.checks += 1
        if not self.valid_input:
            raise ValueError('Input changed')

    def terminal(self, job):
        self.verify_input(job)
        self.calls += 1
        return json.loads(self.path.read_text()), dict(
            path=str(self.path), sha256='sha256:' + digest(self.path))


def test_reuse_keeps_return_independent_and_rechecks_source(tmp_path):
    source = Source(tmp_path / 'terminal.json')
    port = TerminalReuse(source)
    first = port.terminal({'job': 1})
    first[0]['nested']['a'] = 900
    second = port.terminal({'job': 1})
    assert second[0]['nested']['a'] == 1
    assert (source.calls, source.checks, port.hits) == (1, 2, 1)


def test_changed_input_cannot_be_hidden_by_unchanged_terminal(tmp_path):
    source = Source(tmp_path / 'terminal.json')
    port = TerminalReuse(source)
    port.terminal({})
    source.valid_input = False
    with pytest.raises(ValueError, match='Input changed'):
        port.terminal({})


def test_changed_terminal_is_fully_validated_again(tmp_path):
    source = Source(tmp_path / 'terminal.json')
    port = TerminalReuse(source)
    port.terminal({})
    source.path.write_text('{"state":"complete","nested":{"a":2}}')
    assert port.terminal({})[0]['nested']['a'] == 2
    assert source.calls == 2
    source.path.write_text('corrupt')
    with pytest.raises(ValueError):
        port.terminal({})


def test_deleted_file_and_changed_job_never_hit(tmp_path):
    source = Source(tmp_path / 'terminal.json')
    port = TerminalReuse(source)
    port.terminal({'job': 1})
    port.terminal({'job': 2})
    assert source.calls == 2
    source.path.unlink()
    with pytest.raises(FileNotFoundError):
        port.terminal({'job': 1})


def test_mutation_during_read_is_rejected(tmp_path):
    source = Source(tmp_path / 'terminal.json')
    original = source.terminal

    def mutate(job):
        result = original(job)
        source.path.write_text('{"changed":true}')
        return result

    source.terminal = mutate
    with pytest.raises(ValueError, match='changed during'):
        TerminalReuse(source).terminal({})


def test_new_operation_has_no_old_cache(tmp_path):
    source = Source(tmp_path / 'terminal.json')
    TerminalReuse(source).terminal({})
    TerminalReuse(source).terminal({})
    assert source.calls == 2


def test_symlink_replacement_reenters_original_confinement_checks(tmp_path):
    source = Source(tmp_path / 'terminal.json')
    port = TerminalReuse(source)
    port.terminal({})
    target = tmp_path / 'elsewhere.json'
    target.write_bytes(source.path.read_bytes())
    source.path.unlink()
    source.path.symlink_to(target)

    def confined_read(job):
        raise ValueError('Original confinement check')

    source.terminal = confined_read
    with pytest.raises(ValueError, match='Original confinement'):
        port.terminal({})
    assert port.hits == 0


def test_nested_reuse_still_rejects_changed_native_ancestor(tmp_path):
    native = Source(tmp_path / 'native.json')
    upstream = TerminalReuse(native)
    downstream = Source(tmp_path / 'downstream.json')
    original_check = downstream.verify_input

    def verify(job):
        original_check(job)
        upstream.terminal(job)

    downstream.verify_input = verify
    port = TerminalReuse(downstream)
    port.terminal({})
    port.terminal({})
    native.valid_input = False
    with pytest.raises(ValueError, match='Input changed'):
        port.terminal({})
