"""Reuse exact track-phase interpolation across certified salvage candidates."""

from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np


FINE_PIN = '7ccb39db8f2f4a278b2c7b1977866e3d731601de7d759adb5541e88692917f09'
PHASE_PIN = '693a580ccbf8b134858448e4700a9b495dc5b9cc301b7ffc3a1e5dae4fab847d'


class ShadowMismatch(BaseException):
    """Prevent a silent alternate inference when a matched check diverges."""


class PreparedFinePhase:
    """Same flattened phase/observation order as the original tiled lookup."""

    def __init__(self, bank, times, phases):
        from leo.analysis.research.continuous_curve_fit import EARTH_ROTATION_RAD_S

        self.states = tuple(np.asarray(bank[key]) for key in ('position_km','velocity_km_s'))
        knots = np.asarray(bank['time_s'])
        t, phi = np.asarray(times), np.asarray(phases)
        if (knots.ndim != 1 or len(knots) < 2 or t.ndim != 1 or phi.ndim != 1
                or not all(a.dtype == np.float64 for a in (knots,t,phi,*self.states))
                or len({a.shape for a in self.states}) != 1 or self.states[0].ndim != 3
                or self.states[0].shape[1:] != (len(knots),3)
                or not all(np.isfinite(a).all() for a in (knots,t,phi)) or np.any(np.diff(knots) <= 0.)):
            raise ValueError('Unsupported original phase interpolation domain')
        label = np.repeat(np.arange(len(phi)),len(t))
        requested = np.tile(t,len(phi)) + phi[label]
        if np.any(requested < knots[0]) or np.any(requested > knots[-1]):
            raise ValueError('Phase interpolation never extrapolates')
        self.index = np.clip(np.searchsorted(knots,requested,side='right')-1,0,len(knots)-2)
        index = self.index
        self.fraction = ((requested-knots[index]) / (knots[index+1]-knots[index]))[:,None]
        angle = EARTH_ROTATION_RAD_S * phi[label]
        self.cosine,self.sine = np.cos(angle),np.sin(angle)
        self.size = len(phi),len(t)
        self.replicated_bytes = len(phi)*sum(state.shape[1]*state.shape[2]*state.dtype.itemsize for state in self.states)

    def project(self, j, coordinates):
        from leo.analysis.research.continuous_curve_fit import phase_frequency_from_states

        index = self.index
        output = []
        for source in self.states:
            values = source[j,index] + self.fraction * (source[j,index+1]-source[j,index])
            x,y = values[:,0].copy(),values[:,1].copy()
            values[:,0] = self.cosine*x-self.sine*y
            values[:,1] = self.sine*x+self.cosine*y
            output.append(values)
        return tuple(a.reshape(self.size) for a in phase_frequency_from_states(*output,*coordinates))


def exact_port(original):
    from leo.analysis.research import continuous_curve_fit as phase

    paths = ((Path(original.__code__.co_filename),FINE_PIN),(Path(phase.__file__),PHASE_PIN))
    if any(sha256(path.read_bytes()).hexdigest() != pin for path,pin in paths):
        raise ValueError('Unexpected certified fine search or original phase interpolation source')
    source = getsource(original)
    old_prep = '    times, labels = np.tile(t, len(grid)), np.repeat(np.arange(len(grid)), tail)\n'
    last = '        witness = algo08_salvage_bound.EndpointWitness.prepare'
    begin = '        bank = dict(time_s=scan.sky["time_s"],'
    if any(source.count(anchor) != 1 for anchor in (old_prep,begin,last)):
        raise ValueError('The original fine salvage boundaries changed')
    prep = '''    if kernel.paired_phase_frequency is not _paired:
        counts["phase_port_fallbacks"] += 1
        return original(stock, counts, kernel, scan, track, y, noise, rf, shortlist, coordinates)
    try:
        prepared = _prepared(scan.sky, t, grid)
    except ValueError:
        counts["phase_domain_fallbacks"] += 1
        return original(stock, counts, kernel, scan, track, y, noise, rf, shortlist, coordinates)
    counts["prepared_tracks"] += 1
'''
    # The original operation bills support trials before checking its geometry.
    # Undo that accounting if the bound port delegates the entire operation.
    prep = prep.replace('        return original(', '        counts["support_trials"] -= trials\n        return original(')
    source = source.replace(old_prep,prep)
    replacement = '''        f, e = prepared.project(j, coordinates)
        counts["prepared_satellites"] += 1
        counts["avoided_logical_bank_bytes"] += prepared.replicated_bytes
'''
    source = source[:source.index(begin)] + replacement + source[source.index(last):]
    scope = dict(original.__globals__, original=original, _prepared=PreparedFinePhase, _paired=phase.paired_phase_frequency)
    exec(compile(source,original.__code__.co_filename,'exec'),scope)
    return scope[original.__name__]


def measured_fine(original, candidate, audit):
    def evaluate(stock, counts, kernel, scan, track, y, noise, rf, shortlist, coordinates):
        index = len(audit)
        modes = ('control','candidate') if index % 2 == 0 else ('candidate','control')
        times, answers, work = {},{},{}
        for mode in modes:
            counter = Counter()
            start, wall = process_time_ns(),perf_counter_ns()
            operation = original if mode == 'control' else candidate
            answers[mode] = operation(stock,counter,kernel,scan,track,y,noise,rf,shortlist,coordinates)
            times[mode] = dict(cpu_ns=process_time_ns()-start,elapsed_ns=perf_counter_ns()-wall)
            work[mode] = dict(counter)
        if answers['control'] != answers['candidate']:
            raise ShadowMismatch(f"Certified alternatives changed for {track['key']}")
        counts.update(work['candidate'])
        audit.append(dict(track=track['key'],order=modes,clocks=times,counters=work,supports=answers['candidate'][1],
                          alternatives=len(answers['candidate'][0])))
        return answers['candidate']
    return evaluate


@contextmanager
def binding(audit):
    import certified_salvage as released

    original = released.fine_alternatives
    candidate = exact_port(original)
    with patch.object(released,'fine_alternatives',measured_fine(original,candidate,audit)):
        yield
