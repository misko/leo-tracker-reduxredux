"""Own causal row election at one verified live preparation boundary."""

from contextlib import contextmanager
from functools import wraps
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from types import CodeType, FunctionType
from unittest.mock import patch


ORBIT_SHA = "6d2b3db52f68abb93bd3a72211e6e8bc6030d5b939981287922a2beebc4f028d"


class UnownedBank(Exception):
    """A reviewed preparation did not consume its observed bank."""


def named_code(scope, name):
    result, = [member for member in scope.co_consts if type(member) is CodeType and member.co_name == name]
    return result


def approved_code(path, pin, *parts):
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if sha256(raw).hexdigest() != pin:
        return None
    code = compile(raw, str(path), "exec", dont_inherit=True)
    for name in parts:
        code = named_code(code, name)
    return code


def declared(operation, path, code):
    return (code is not None and type(operation) is FunctionType
            and Path(operation.__code__.co_filename).resolve() == path and operation.__code__ == code)


class LiveRegional:
    """Verify the actual installed regional alias and each reviewed observing closure."""

    def __init__(self, live_path, live_pin):
        import historical_orbit_index as historical
        from empty_bootstrap import RELEASE

        self.path = live_path.resolve()
        self.live = approved_code(self.path, live_pin, "corner_support", "regional")
        self.stock_path = RELEASE/"src/leo/analysis/localization_v3/orbits.py"
        self.stock = approved_code(self.stock_path, ORBIT_SHA, "regional_bank")
        self.inputs_path = RELEASE/"src/leo/operations/localization_v3_inputs.py"
        self.initial = approved_code(self.inputs_path, historical.INPUTS_PIN, "prepare_initial_sky")

    def owners(self, operation):
        """Obtain the real observation slots without installing a competing bank port."""
        stack = []
        while declared(operation, self.path, self.live):
            variables = dict(zip(operation.__code__.co_freevars, operation.__closure__, strict=True))
            owner = variables["nominal"].cell_contents
            if type(owner) is not dict or any(previous is owner for previous in stack) or len(stack) == 4:
                return None
            stack.append(owner)
            operation = variables["original_bank"].cell_contents
        return tuple(stack) if declared(operation, self.stock_path, self.stock) else None


def bind_one(ordinary, audit, reviewed):
    """Call one installed preparation with both election and actual live capture."""
    @wraps(ordinary)
    def prepare(*args, **kwargs):
        import historical_orbit_index as historical
        from causal_body_election import binding as election
        from leo.operations import localization_v3_inputs as inputs

        start_cpu, start_wall = process_time_ns(), perf_counter_ns()
        row = dict(observed_regional_calls=0, expected_phase_handoffs=0, same_phase_handoffs=0)
        audit.setdefault("attempts", []).append(row)
        prior_alias = inputs.regional_bank
        owners = reviewed.owners(prior_alias)
        if not owners or not declared(inputs.prepare_initial_sky, reviewed.inputs_path, reviewed.initial):
            row["fallback"] = "unverified active regional or initial port"
            row["admission_cpu_ns"] = process_time_ns() - start_cpu
            return ordinary(*args, **kwargs)
        row["active_observers"] = len(owners)
        ordinary_phase = historical.phase_history
        token = None
        try:
            with election(row):
                elected_initial, elected_phase = inputs.prepare_initial_sky, historical.phase_history
                if not row["admissible_source"]:
                    row["fallback"] = "unverified election source"

                @wraps(elected_initial)
                def initial(reader, tracks, metadata, *, element_parser, **options):
                    nonlocal token
                    if inputs.regional_bank is not prior_alias or token is not None:
                        raise UnownedBank("regional authority changed within preparation")
                    sky = elected_initial(reader, tracks, metadata, element_parser=element_parser, **options)
                    bank = sky["bank"]
                    elements = sky["nominal_elements"]
                    origin = metadata["anchor_utc_ns"]
                    numbers = tuple(map(int, elements))
                    if (tuple(map(int, bank["norad"])) != numbers or any(
                        owner.get("bank") is not bank or owner.get("origin") != origin
                        or tuple(owner["catalogue"].satellite_numbers) != numbers for owner in owners
                    )):
                        raise UnownedBank("installed initial sky did not own the observed bank")
                    row["observed_regional_calls"] += 1
                    row["regional_rows"] = len(numbers)
                    owner = getattr(element_parser, "__self__", element_parser)
                    if type(owner) is historical.VerifiedIndexReader:
                        row["expected_phase_handoffs"] += 1
                        token = reader, metadata, element_parser, elements, bank, metadata["causal_cutoff_utc_ns"], origin
                    return sky

                @wraps(elected_phase)
                def phase(reader, elements, metadata, *, element_parser, **options):
                    nonlocal token
                    saved, token = token, None
                    if (saved is None or reader is not saved[0] or metadata is not saved[1]
                            or element_parser is not saved[2] or elements is not saved[3]
                            or metadata["causal_cutoff_utc_ns"] != saved[5]
                            or metadata["anchor_utc_ns"] != saved[6]
                            or any(owner.get("bank") is not saved[4] for owner in owners)):
                        raise UnownedBank("phase history did not consume the observed initial sky")
                    row["same_phase_handoffs"] += 1
                    return elected_phase(reader, elements, metadata, element_parser=element_parser, **options)

                row["admission_cpu_ns"] = process_time_ns() - start_cpu
                if not row["admissible_source"]:
                    return ordinary(*args, **kwargs)
                with (patch.object(inputs, "prepare_initial_sky", initial),
                      patch.object(historical, "phase_history", phase)):
                    result = ordinary(*args, **kwargs)
                if (result["status"] == "inputs_prepared"
                        and row["same_phase_handoffs"] != row["expected_phase_handoffs"]):
                    raise UnownedBank("complete preparation omitted its original phase consumer")
                return result
        except UnownedBank as error:
            row.update(fallback=str(error), abandoned_cpu_ns=process_time_ns()-start_cpu,
                       abandoned_wall_ns=perf_counter_ns()-start_wall)
        finally:
            row.update(scoped_cpu_ns=process_time_ns()-start_cpu, scoped_wall_ns=perf_counter_ns()-start_wall)
        # Both lexical election and bank handoff patches have been unwound.
        if historical.phase_history is not ordinary_phase:
            raise RuntimeError("The causal phase boundary did not restore its original owner")
        return ordinary(*args, **kwargs)

    return prepare


@contextmanager
def binding(audit):
    """Opt in around the same saved or raw research publisher's exact ports."""
    import historical_orbit_index as historical
    from solver_exception_0022 import GUARD, GUARD_PIN

    started = process_time_ns()
    reviewed = LiveRegional(GUARD, GUARD_PIN)
    audit["verified_source_cpu_ns"] = process_time_ns() - started
    factory = historical.guarded_preparation

    @wraps(factory)
    def checked_preparation(*args, **kwargs):
        return bind_one(factory(*args, **kwargs), audit, reviewed)

    with patch.object(historical, "guarded_preparation", checked_preparation):
        yield
