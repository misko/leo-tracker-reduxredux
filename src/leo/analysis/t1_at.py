"""Top-1 absolute-timing greedy + one-out/greedy-many-in association.

No orbit, IO, storage or calibration dependencies. The immutable input carries
visible, calibrated timing hypotheses from a separately qualified producer.
The count objective is primary; the Gaussian proxy only breaks count ties.
"""

import time
from dataclasses import dataclass

import numpy as np

from leo.contracts.t1_at import T1AtCandidateV1, T1AtInputV1


def top_candidates(candidates: tuple[T1AtCandidateV1, ...]) -> tuple[T1AtCandidateV1, ...]:
    winners: dict[str, T1AtCandidateV1] = {}
    for candidate in candidates:
        key = (candidate.refined_margin, -candidate.candidate_id)
        previous = winners.get(candidate.window_id)
        if previous is None or key > (previous.refined_margin, -previous.candidate_id):
            winners[candidate.window_id] = candidate
    return tuple(sorted(winners.values(), key=lambda c: c.candidate_id))


@dataclass(frozen=True)
class _Support:
    rows: tuple[int, ...]
    errors: tuple[float, ...]
    tie_score: float

    @property
    def count(self):
        return len(self.rows)


class _Search:
    def __init__(self, candidates, modes, deadline):
        self.candidates, self.modes, self.deadline = candidates, modes, deadline
        self.times = np.array([c.receive_time_s for c in candidates])
        lookup = {c.candidate_id: i for i, c in enumerate(candidates)}
        self.lanes, self.row_modes, self.catalog_modes = [], [set() for _ in candidates], {}
        for index, mode in enumerate(modes):
            grouped = {}
            self.catalog_modes.setdefault(mode.catalog_number, set()).add(index)
            for cid, error in zip(mode.candidate_ids, mode.residual_hz, strict=True):
                if cid not in lookup:
                    continue
                row = lookup[cid]
                candidate = candidates[row]
                grouped.setdefault((candidate.receiver_id, candidate.channel), []).append(
                    (row, error)
                )
                self.row_modes[row].add(index)
            self.lanes.append(
                [sorted(grouped[key], key=lambda pair: abs(pair[1])) for key in sorted(grouped)]
            )

    def check(self):
        if time.monotonic() >= self.deadline:
            raise TimeoutError("T1-AT bounded selection deadline reached; no complete product")

    def evaluate(self, index, used):
        self.check()
        selected = []
        for lane in self.lanes[index]:
            free = [(r, e) for r, e in lane if not used[r]]
            # Historical code sorts unique window groups before stable time sort.
            # Top-1 guarantees groups are unique; retain deterministic row ties.
            free.sort(key=lambda pair: (self.times[pair[0]], pair[0]))
            breaks = (
                [0]
                + [
                    j
                    for j in range(1, len(free))
                    if self.times[free[j][0]] - self.times[free[j - 1][0]] > 5
                ]
                + [len(free)]
            )
            for start, stop in zip(breaks[:-1], breaks[1:], strict=True):
                part = free[start:stop]
                if len(part) >= 10 and self.times[part[-1][0]] - self.times[part[0][0]] >= 5:
                    selected.extend(part)
        sse = sum(e * e for _, e in selected)
        return _Support(
            tuple(r for r, _ in selected),
            tuple(e for _, e in selected),
            -0.5 * sse / 200**2 - 0.5 * self.modes[index].absolute_timing_s ** 2,
        )

    def affected(self, rows):
        return {index for row in rows for index in self.row_modes[row]}

    @staticmethod
    def objective(chosen):
        return sum(support.count for _, support in chosen.values()) - 10 * len(chosen)

    def refresh(self, indices, chosen, used, cache, forbidden=frozenset()):
        for index in sorted(indices):
            number = self.modes[index].catalog_number
            if number not in chosen and number not in forbidden:
                cache[index] = self.evaluate(index, used)

    def fill(self, chosen, used, cache, forbidden=frozenset()):
        while True:
            self.check()
            possible = [
                i
                for i, m in enumerate(self.modes)
                if m.catalog_number not in chosen
                and m.catalog_number not in forbidden
                and cache[i].count > 10
            ]
            if not possible:
                return
            index = max(
                possible,
                key=lambda i: (
                    cache[i].count,
                    cache[i].tie_score,
                    -self.modes[i].catalog_number,
                    -i,
                ),
            )
            support = cache[index]
            chosen[self.modes[index].catalog_number] = index, support
            used[list(support.rows)] = True
            self.refresh(self.affected(support.rows), chosen, used, cache, forbidden)

    def export(self, chosen):
        assignments, satellites = [], []
        for number, (index, support) in chosen.items():
            mode = self.modes[index]
            satellites.append(
                dict(
                    catalog_number=number,
                    absolute_timing_s=mode.absolute_timing_s,
                    mode_index=index,
                    count=support.count,
                )
            )
            assignments.extend(
                dict(
                    candidate_id=self.candidates[r].candidate_id,
                    window_id=self.candidates[r].window_id,
                    catalog_number=number,
                    mode_index=index,
                    residual_hz=e,
                )
                for r, e in zip(support.rows, support.errors, strict=True)
            )
        count = len(assignments)
        assert len({a["window_id"] for a in assignments}) == count
        return dict(
            assigned=count,
            denominator=len(self.candidates),
            unassigned=len(self.candidates) - count,
            satellites=satellites,
            objective=self.objective(chosen),
            assignments=assignments,
        )

    def run(self):
        used = np.zeros(len(self.candidates), bool)
        chosen = {}
        cache = [self.evaluate(i, used) for i in range(len(self.modes))]
        self.fill(chosen, used, cache)
        initial = self.export(chosen)
        passes = []
        for sweep in range(3):
            accepted = 0
            for number in list(chosen):
                self.check()
                if number not in chosen:
                    continue
                _, removed = chosen[number]
                trial = {n: v for n, v in chosen.items() if n != number}
                trial_used, trial_cache = used.copy(), cache.copy()
                trial_used[list(removed.rows)] = False
                self.refresh(self.affected(removed.rows), trial, trial_used, trial_cache, {number})
                self.fill(trial, trial_used, trial_cache, {number})
                if self.objective(trial) > self.objective(chosen):
                    self.refresh(self.catalog_modes[number], trial, trial_used, trial_cache)
                    self.fill(trial, trial_used, trial_cache)
                    chosen, used, cache = trial, trial_used, trial_cache
                    accepted += 1
            passes.append(
                dict(pass_index=sweep + 1, accepted=accepted, objective=self.objective(chosen))
            )
            if not accepted:
                break
        return dict(
            initial=initial,
            final=self.export(chosen),
            passes=passes,
            termination="no_improving_greedy_repair" if not accepted else "pass_limit",
        )


def select_timing_modes(candidates, modes, *, maximum_seconds: float = 120) -> dict:
    """Select from already top-one window/timing evidence, independent of location.

    This numerical port also serves regional callers. It makes no known-site or
    calibration claim; the caller owns those separately versioned input contracts.
    """
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1800:
        raise ValueError("selection budget must be in (0, 1800] seconds")
    if len({c.window_id for c in candidates}) != len(candidates):
        raise ValueError("selection requires one candidate per window")
    ids = {c.candidate_id for c in candidates}
    if len(ids) != len(candidates):
        raise ValueError("selection requires unique candidate IDs")
    if any(not set(mode.candidate_ids) <= ids for mode in modes):
        raise ValueError("selection mode references an unknown candidate")
    return _Search(candidates, modes, time.monotonic() + maximum_seconds).run()


def associate(source: T1AtInputV1, *, maximum_seconds: float = 120) -> dict:
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1800:
        raise ValueError("selection budget must be in (0, 1800] seconds")
    candidates = top_candidates(source.candidates)
    deadline = time.monotonic() + maximum_seconds
    arms = {
        arm: _Search(candidates, modes, deadline).run()
        for arm, modes in (("fitted-c", source.fitted_c_modes), ("zero-c", source.zero_c_modes))
    }
    return dict(
        baseline_id="t1_at_v1",
        session_id=source.session_id,
        arms=arms,
        candidate_only=True,
        identity_claimed=False,
        scope="Known-site conditional association; not blind localization or held-out validation",
    )
