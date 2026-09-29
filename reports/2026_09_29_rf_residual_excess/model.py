"""Candidate excess above contemporaneous donor receiver/RF residuals."""

from collections import defaultdict

import numpy as np


class Evidence:
    def __init__(self, donors, shuffle=False):
        self.cells = defaultdict(list)
        self.ends = {}
        self.unchanged_labels = 0
        self.rotated_cases = 0
        for row in donors:
            key = (row["unit_id"], row["receiver_id"], row["rf_hz"])
            self.cells[key].append(dict(row))
            self.ends[row["unit_id"]] = row["available_utc_ns"]
        for rows in self.cells.values():
            rows.sort(key=lambda r: (r["number"], r["session_id"], r["track_id"]))
            if shuffle and len(rows) > 1:
                old = [r["shape"]["slope"] for r in rows]
                self.rotated_cases += len(rows)
                self.unchanged_labels += sum(
                    rows[i]["number"] == rows[(i - 1) % len(rows)]["number"]
                    for i in range(len(rows))
                )
                for i, r in enumerate(rows):
                    r["shape"] = dict(slope=old[(i - 1) % len(rows)])
        self.excess = defaultdict(dict)
        for (group, rx, rf), rows in sorted(self.cells.items()):
            bynumber = defaultdict(list)
            for r in rows:
                bynumber[r["number"]].append(r["shape"]["slope"])
            for number, slopes in bynumber.items():
                if len(bynumber) - 1 < 2:
                    continue
                # Equal weight per other candidate, then per RF lane and group.
                baseline = float(
                    np.median([np.median(v) for n, v in bynumber.items() if n != number])
                )
                excess = float(np.median(slopes)) - baseline
                self.excess[rx, number].setdefault(group, []).append((rf, excess))

    def predict(self, target):
        rx, number = target["receiver_id"], target["number"]
        groups = []
        deltas = []
        for group, lanes in sorted(self.excess[rx, number].items()):
            if self.ends[group] >= target["start_utc_ns"]:
                continue
            groups.append(group)
            deltas.append(float(np.median([v for rf, v in lanes])))
        controls = []
        controlgroups = []
        for (group, r, rf), rows in sorted(self.cells.items()):
            if r != rx or rf != target["rf_hz"] or self.ends[group] >= target["start_utc_ns"]:
                continue
            bynumber = defaultdict(list)
            for row in rows:
                if row["number"] != number:
                    bynumber[row["number"]].append(row["shape"]["slope"])
            if len(bynumber) < 2:
                continue
            controlgroups.append(group)
            controls.append(float(np.median([np.median(v) for v in bynumber.values()])))
        if len(groups) < 2 or len(controlgroups) < 2:
            return None
        baseline = float(np.median(controls))
        delta = float(np.median(deltas))
        return dict(
            candidate_groups=groups,
            candidate_group_excess=deltas,
            rf_groups=controlgroups,
            rf_group_slopes=controls,
            rf_slope=baseline,
            excess_slope=delta,
            total_slope=baseline + delta,
        )
