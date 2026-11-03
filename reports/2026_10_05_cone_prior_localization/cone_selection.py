"""Soft positive-receiver evidence in the existing greedy/replacement port.

Top-one inputs cannot prove absence of a satellite on the peer receiver.
Consequently this prototype uses the observed receiver's conditional marginal,
not an RX-only label fabricated from missing top-one matches. Average log odds
within each satellite/5s block, then sum blocks. The original lane coherence,
600 Hz gate, satellite cost, timing pool and replacement neighborhood remain.
"""
import numpy as np
from penalty_replace_search import Search
from cone_geometry import cone_marginals
from cone_objective import directions
from types import SimpleNamespace


def add_evidence(modes, records, raw, theta, frames, support, null_marginals):
    for mode, record in zip(modes, records):
        rows = np.asarray(mode['rows'], int); sat = int(record['satellite_index'])
        scores = np.zeros(len(raw.times))
        if len(rows):
            part = SimpleNamespace(times=raw.times[rows], numbers=raw.numbers[sat:sat+1],
                position=raw.position[sat:sat+1], nodes=raw.nodes)
            physical = np.r_[raw.initial[:6], record['offset_s']]
            unit = directions(part, physical, derivatives=False)[:, 0]
            marginal, _ = cone_marginals(unit, theta, frames)
            value = marginal[np.arange(len(rows)), raw.receiver[rows]]
            confidence, _ = support.evaluate(unit)
            scores[rows] = confidence*np.clip(np.log(np.maximum(value, 1e-6)/
                                                     null_marginals[raw.receiver[rows]]), -3., 3.)
        mode['sky_log_odds'] = scores


class ConeSearch(Search):
    def __init__(self, *args, strength=1., **kwargs):
        self.strength = float(strength)
        super().__init__(*args, **kwargs)

    def evaluate(self, i, used):
        v = super().evaluate(i, used)
        rows = np.asarray(v['rows'], int)
        if self.strength and len(rows):
            _, inv = np.unique(np.floor(self.times[rows]/5.), return_inverse=True)
            values = self.modes[i]['sky_log_odds'][rows]
            v['sky_score'] = float(np.sum(np.bincount(inv, weights=values)/np.bincount(inv)))
        else:
            v['sky_score'] = 0.
        return v

    def objective(self, chosen):
        return super().objective(chosen)+self.strength*sum(v['sky_score'] for v in chosen.values())

    def fill(self, chosen, used, cache, forbidden=frozenset()):
        if not self.strength:
            return super().fill(chosen, used, cache, forbidden)
        additions = []
        while True:
            gains = [v['count']-self.penalty+self.strength*v['sky_score'] for v in cache]
            valid = [i for i, m in enumerate(self.modes) if m['catalog_number'] not in chosen
                     and m['catalog_number'] not in forbidden and cache[i]['count']>=self.minimum
                     and gains[i]>1e-10]
            if not valid:
                break
            i = max(valid, key=lambda j: (gains[j], cache[j]['score'], -self.modes[j]['catalog_number'], -j))
            number = self.modes[i]['catalog_number']
            v = dict(cache[i], mode_index=i, catalog_number=number)
            assert not used[v['rows']].any()
            before = self.objective(chosen)
            chosen[number] = v; used[v['rows']] = True
            after = self.objective(chosen)
            assert after>before and abs(after-before-gains[i])<1e-7
            additions.append(dict(catalog_number=number, mode_index=i, added=v['count'],
                                  marginal_score=gains[i], objective=after))
            self.refresh(self.affected(v['rows']), chosen, used, cache, forbidden)
        return additions

    def export(self, chosen):
        r = super().export(chosen)
        r['sky_score'] = sum(v['sky_score'] for v in chosen.values())
        r['coverage_score'] = r['assigned']-self.penalty*r['satellites']
        return r
