"""A single-slate bounded soft fit with absolute CFO and shared phase priors."""

from collections import Counter
from time import process_time_ns

import numpy as np
from scipy.special import logsumexp


K = 4
ROUNDS = 6
ARC_BIAS = 300.
NULL_BIAS = 1. / (4.4e-6 * np.sqrt(12.))


class ArcNoise:
    def __init__(self, sigma, bias):
        self.inverse = 1. / np.asarray(sigma)
        self.weights = self.inverse**2
        self.precision = float(self.weights.sum())
        self.mean_sigma = np.sqrt(1./self.precision + bias**2)
        self.logdet = float(2*np.log(sigma).sum() + np.log1p(bias**2*self.precision))

    def whiten(self, data):
        mean = (data @ self.weights) / self.precision
        return np.concatenate(((data-mean[..., None])*self.inverse, (mean/self.mean_sigma)[..., None]), axis=-1)

    def log_density(self, data):
        normalized = self.whiten(data)
        return -.5*((normalized**2).sum(axis=-1) + self.logdet + len(self.inverse)*np.log(2*np.pi))


def subset(bank, labels):
    return {key: bank[key][labels] for key in ("position_km", "velocity_km_s")} | {"time_s": bank["time_s"]}


def nominate(values, frequency, tangent, elevation, ivar, widths):
    residual = values - frequency
    weights = ivar / ivar.sum()
    raw_mean = (residual @ weights)[:, None]
    tangent_mean = (tangent @ weights)[:, None]
    centered, change = (residual-raw_mean)*np.sqrt(ivar), (tangent-tangent_mean)*np.sqrt(ivar)
    precision = 1. / widths**2
    phase = np.clip((centered*change).sum(axis=1) / ((change**2).sum(axis=1)+precision), -15., 15.)
    score = ((centered-change*phase[:, None])**2).sum(axis=1) + precision*phase**2
    visible = (elevation >= -3.).all(axis=1) & np.isfinite(score)
    return score, visible


def radio_design(track, scan, i):
    from leo.analysis.research.retained_track_likelihood import PERIOD

    times, rf = track["times"], track["rf_hz"]
    n = len(times)
    rx, band = track["receiver"]-1, int(track["channel"] > 4)
    width = scan.rx_basis[i].shape[1]
    design = np.zeros((n, 9+2*width))
    design[:, 2*rx + band] = PERIOD / np.sqrt(12.)
    design[:, 4+2*rx] = (times-150.)*10.
    design[:, 5+2*rx] = (times-150.) * (-.5 if band == 0 else .5)
    design[:, 8] = (rf/1e9-11.5)*200_000.
    design[:, 9+rx*width:9+(rx+1)*width] = (rf/11.5e9) * scan.rx_basis[i]*200.
    return design


class Slate:
    def __init__(self, scan, model):
        from leo.analysis.localization_v3 import scan as scan_kernel
        from leo.analysis.localization_v3.history_position import forecast_phase_mean
        from leo.analysis.localization_v3.retained_position import phase_widths
        from leo.analysis.research.retained_track_likelihood import PERIOD

        self.scan, self.core = scan, scan_kernel.phase_linear_frequency
        self.region = scan.search_region
        self.half = self.region.half_width_km
        self.period = PERIOD
        self.work = Counter()
        self.radio_width = 9 + 2*scan.rx_basis[0].shape[1]
        f, e, h = self.core(scan.geometry, *self.region.latlon(np.zeros(2)))
        all_tracks = [i for i, track in enumerate(scan.tracks) if len(track["times"]) >= 6]
        curved = set(scan.curved)
        if not curved:
            raise ValueError("No active curved arcs")
        noise = scan.fixed_window_noise
        widths = np.maximum(1., scan.sigma)
        pool = None
        rows = []
        for indices in (sorted(curved), [i for i in all_tracks if i not in curved]):
            labels = np.arange(len(scan.norads)) if pool is None else np.array(sorted(pool), dtype=int)
            if not len(labels):
                break
            selected = set()
            for i in indices:
                track = scan.tracks[i]
                columns, q = scan.index[i], track["rf_hz"]/11.5e9
                ids = track["observation_ids"]
                sigma = np.asarray([noise["per_observation_noise_sigma_hz"][j] for j in ids]) if (
                    noise["extra_parameter_BIC_gain"] > 0) else np.full(len(ids), scan.radio_sigma_hz)
                if i not in curved:
                    sigma = sigma*np.sqrt(2.)
                ix = np.ix_(labels, columns)
                score, visible = nominate(track["values"], q*f[ix], q*h[ix], e[ix], 1/sigma**2, widths[labels])
                allowed = np.flatnonzero(visible)
                rivals = labels[allowed[np.argsort(score[allowed], kind="stable")[:K]]]
                selected.update(rivals)
                self.work.update(discovery_orbits=len(labels), discovery_epoch_rows=len(labels)*len(ids))
                if len(rivals):
                    covariance = ArcNoise(sigma, ARC_BIAS)
                    clutter = float(np.log(.10) + ArcNoise(np.maximum(sigma, 450.), NULL_BIAS).log_density(track["values"]))
                    rows.append(dict(i=i, labels=rivals, columns=columns, values=track["values"], q=q, ids=ids,
                                     curved=i in curved, design=radio_design(track, scan, i), covariance=covariance, clutter=clutter))
            if pool is None:
                pool = selected
        if not rows:
            raise ValueError("No visible causal hypotheses at the offered centre")
        self.labels = np.array(sorted({j for row in rows for j in row["labels"]}), dtype=int)
        phase_width, evidence = phase_widths(scan, self.labels.tolist())
        self.mean = forecast_phase_mean(evidence, model["shrinkage"])
        self.width = phase_width*float(model["multiplier"])
        self.geometry = scan_kernel.prepare_phase_geometry(subset(scan.sky, self.labels), scan.times, self.mean)
        f, _, _ = self.core(self.geometry, *self.region.latlon(np.zeros(2)))
        for row in rows:
            row["local"] = np.searchsorted(self.labels, row["labels"])
            nominal = row["q"]*f[np.ix_(row["local"], row["columns"])]
            mean_offset = ((nominal-row["values"]) @ row["covariance"].weights)/row["covariance"].precision
            row["aliases"] = np.rint(mean_offset/self.period).astype(int)[:, None] + np.arange(-1, 2)
            row["log_prior"] = np.log(.90/row["aliases"].size)
        self.rows = rows

    def geometry_at(self, point):
        self.work.update(refinement_geometry_calls=1)
        return self.core(self.geometry, *self.region.latlon(point))

    def evaluate(self, point, beta, radio, *, derivatives=False):
        f, e, h = self.geometry_at(point)
        if derivatives:
            offsets = np.eye(2)*.010
            shifts = [self.geometry_at(np.clip(point + offset, -self.half, self.half)) for offset in offsets]
            for i, offset in enumerate(offsets):
                if point[i]+offset[i] > self.half:
                    shifts[i] = self.geometry_at(point-offset)
                    offsets[i, i] *= -1
        phases = beta[len(radio):]*self.width
        cost = .5 * float(beta @ beta)
        width = 2 + len(beta)
        gram, rhs, records = np.eye(width), np.r_[np.zeros(2), -beta], []
        gram[:2, :2] *= 1e-6
        for row in self.rows:
            local, columns, q = row["local"], row["columns"], row["q"]
            ix = np.ix_(local, columns)
            design, covariance = row["design"][:, radio], row["covariance"]
            nominal = q*(f[ix]+h[ix]*phases[local, None])
            residual = (row["values"] - design@beta[:len(radio)] - nominal)[:, None, :] + self.period*row["aliases"][..., None]
            # Armed phase bound and original all-observation unshifted horizon.
            horizon = (e[ix] >= 0.).all(axis=1)
            terms = np.where(horizon[:, None], covariance.log_density(residual)+row["log_prior"], -np.inf)
            evidence = logsumexp(np.r_[terms.ravel(), row["clutter"]])
            probabilities = np.exp(terms-evidence)
            cost -= float(evidence)
            if derivatives:
                for j, label in enumerate(local):
                    weight = probabilities[j].sum()
                    if weight < 1e-12:
                        continue
                    matrix = np.zeros((width, len(columns)))
                    for axis, (fs, _, hs) in enumerate(shifts):
                        following = q*(fs[label, columns] + hs[label, columns]*phases[label])
                        matrix[axis] = (following-nominal[j]) / offsets[axis, axis]
                    matrix[2:2+len(radio)] = design.T
                    matrix[2+len(radio)+label] = q*h[label, columns]*self.width[label]
                    nc = covariance.whiten(matrix)
                    gram += weight * (nc @ nc.T)
                    rhs += nc @ (probabilities[j] @ covariance.whiten(residual[j]))
            else:
                j, a = np.unravel_index(np.argmax(probabilities), probabilities.shape)
                r = residual[j, a]
                bias = float((r @ covariance.weights)/(covariance.precision+1/ARC_BIAS**2))
                null = float(np.exp(row["clutter"]-evidence))
                records.append(dict(component=self.scan.tracks[row["i"]]["key"], ids=row["ids"], curved=row["curved"],
                                    norad=int(self.scan.norads[row["labels"][j]]), alias=int(row["aliases"][j, a]),
                                    posterior=float(probabilities[j, a]), clutter=null,
                                    rms_hz=float(np.sqrt(np.mean((r-bias)**2)))))
        self.work.update(soft_likelihood_calls=1)
        return cost, gram, rhs, records

    def fit(self, fitted):
        radio = np.flatnonzero((np.arange(self.radio_width) != 8) | fitted)
        beta = np.zeros(len(radio)+len(self.labels))
        point = np.zeros(2)
        path, accepted = [], 0
        for _ in range(ROUNDS):
            cost, gram, rhs, _ = self.evaluate(point, beta, radio, derivatives=True)
            change = np.linalg.solve(gram, rhs)
            change[:2] *= min(1., 5./max(np.linalg.norm(change[:2], ord=np.inf), 1e-12))
            start = len(radio)
            for ratio in (1., .5, .25):
                trial_point = np.clip(point + ratio*change[:2], -self.half, self.half)
                trial_beta = np.clip(beta + ratio*change[2:], -3., 3.)
                trial_beta[start:] = np.clip(trial_beta[start:], (-15.-self.mean)/self.width, (15.-self.mean)/self.width)
                next_cost, _, _, _ = self.evaluate(trial_point, trial_beta, radio, derivatives=False)
                passed = bool(next_cost < cost - 1e-7)
                path.append(dict(point_km=trial_point, cost=next_cost, accepted=passed))
                if passed:
                    point, beta = trial_point, trial_beta
                    accepted += 1
                    break
            else:
                break
        cost, _, _, records = self.evaluate(point, beta, radio)
        supported = {r["norad"] for r in records if r["curved"] and r["posterior"] >= .5 and r["rms_hz"] <= 450.}
        for row in records:
            row["retained"] = row["norad"] in supported and row["posterior"] >= .5 and row["rms_hz"] <= 450.
        used = [r for r in records if r["retained"]]
        rows = sum(len(r["ids"]) for r in used)
        return dict(point_km=point, latlon=self.region.latlon(point), cost=cost, path=path, accepted_steps=accepted,
                    face=bool(np.max(abs(point)) >= self.half-1e-9), owners=rows, families=len(supported),
                    c_hz_per_ghz=float(200_000.*beta[8]) if fitted else 0., tracks=records,
                    rf_rms_hz=None if not rows else float(np.sqrt(sum(len(r["ids"])*r["rms_hz"]**2 for r in used)/rows)))


def propose(prepared, region, bound):
    from blind_joint_finish import digest, history_model
    from tools.pipeline_eval.variants import v5_core

    started = process_time_ns()
    scan = v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "genuine_previous")
    model, _ = history_model(prepared, scan)
    slate = Slate(scan, model)
    discovery = process_time_ns()-started
    results, clocks = {}, {}
    for arm in ("c0", "fitted_c"):
        started = process_time_ns()
        results[arm] = slate.fit(arm == "fitted_c")
        clocks[arm] = process_time_ns()-started
    return dict(discovery_cpu_ns=discovery, fit_cpu_ns=clocks, arms=results, work=dict(slate.work),
                tracks=len(slate.rows), active_curved_tracks=len(scan.curved), shortlist_bodies=len(slate.labels),
                slate_hypotheses=sum(row["aliases"].size for row in slate.rows), causal_widths_s=slate.width,
                phase_chart_s=slate.mean, elapsed_through_prepared_solver_cpu_ns=discovery+sum(clocks.values()))
