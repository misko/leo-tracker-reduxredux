"""Causal bounded bank of independent known-channel tracks."""

from __future__ import annotations

from dataclasses import dataclass, replace

from tracking import Key, Observation, Policy, Prediction, Tracker, reference_match


@dataclass
class Track:
    track_id: int
    tracker: Tracker
    last_observation: Observation
    last_start_counter: int
    last_margin: float


@dataclass(frozen=True)
class PlannedTrack:
    track_id: int
    prediction: Prediction


@dataclass(frozen=True)
class BankPlan:
    key: Key
    start_counter: int
    visit_index: int
    reason: str
    tracks: tuple[PlannedTrack, ...]
    association_tracks: tuple[PlannedTrack, ...]


@dataclass(frozen=True)
class CacheSelection:
    observation: Observation | None
    selected_track_id: int | None
    accepted_track_ids: tuple[int, ...]
    rejected_track_ids: tuple[int, ...]


def same_identity(left: Observation, right: Observation, rate_hz: int) -> bool:
    return reference_match(left, right, rate_hz)


class MultiTrackBank:
    def __init__(self, policy: Policy | None = None, maximum_tracks: int = 3):
        if type(maximum_tracks) is not int or not 1 <= maximum_tracks <= 3:
            raise ValueError("track capacity must be between one and three")
        self.policy = policy or Policy()
        self.maximum_tracks = maximum_tracks
        self._track_policy = replace(self.policy, discovery_interval=2**31)
        self._tracks: dict[Key, list[Track]] = {}
        self._last_inputs: dict[Key, tuple[int, int]] = {}
        self._accepted_since_discovery: dict[Key, int] = {}
        self._next_track_id = 1
        self._plans: dict[Key, BankPlan] = {}
        self._plan_stages: dict[Key, str] = {}

    def tracks(self, key: Key) -> tuple[Track, ...]:
        return tuple(self._tracks.get(key, ()))

    def accepted_since_discovery(self, key: Key) -> int:
        return self._accepted_since_discovery.get(key, 0)

    def begin(self, key: Key, start_counter: int, visit_index: int) -> BankPlan:
        previous = self._last_inputs.get(key)
        if previous is not None and (start_counter <= previous[0] or visit_index <= previous[1]):
            raise ValueError("bank visits must advance in source time and visit index")
        self._last_inputs[key] = start_counter, visit_index
        planned: list[PlannedTrack] = []
        retained: list[Track] = []
        for track in self._tracks.get(key, []):
            prediction, reason = track.tracker.begin(key, start_counter, visit_index)
            if reason == "expired":
                continue
            retained.append(track)
            if prediction is not None:
                planned.append(PlannedTrack(track.track_id, prediction))
        self._tracks[key] = retained
        association = tuple(planned)
        if self._accepted_since_discovery.get(key, 0) >= self.policy.discovery_interval - 1:
            reason = "periodic_discovery"
            planned = []
        elif not retained:
            reason = "cold"
        elif planned:
            reason = "predicted_bank"
        else:
            reason = "no_supported_prediction"
        by_id = {track.track_id: track for track in retained}
        planned.sort(key=lambda item: (
            -by_id[item.track_id].last_start_counter,
            -by_id[item.track_id].last_margin,
            item.track_id,
        ))
        plan = BankPlan(
            key, start_counter, visit_index, reason, tuple(planned), association
        )
        self._plans[key] = plan
        self._plan_stages[key] = "begun"
        return plan

    def accept_cached(
        self, plan: BankPlan, observations: dict[int, Observation]
    ) -> CacheSelection:
        if (self._plans.get(plan.key) != plan
                or self._plan_stages.get(plan.key) != "begun"):
            raise ValueError("cache selection does not belong to current bank visit")
        tracks = {track.track_id: track for track in self._tracks.get(plan.key, [])}
        planned = {item.track_id: item.prediction for item in plan.tracks}
        if set(observations) - set(planned):
            raise ValueError("observation supplied for an unplanned track")
        accepted: list[tuple[Track, Observation]] = []
        rejected = []
        for item in plan.tracks:
            observation = observations.get(item.track_id)
            track = tracks[item.track_id]
            if observation is not None and track.tracker.accepts(
                plan.key, item.prediction, observation
            ):
                accepted.append((track, observation))
            else:
                rejected.append(item.track_id)
        if not accepted:
            self._plan_stages[plan.key] = "cache_failed"
            return CacheSelection(None, None, (), tuple(rejected))
        accepted.sort(key=lambda item: (-item[1].margin, item[0].track_id))
        for track, observation in accepted:
            if not track.tracker.update(
                plan.key, plan.start_counter, plan.visit_index, observation, discovery=False
            ):
                raise ValueError("accepted cache observation did not update track")
            track.last_observation = observation
            track.last_start_counter = plan.start_counter
            track.last_margin = observation.margin
        self._accepted_since_discovery[plan.key] = (
            self._accepted_since_discovery.get(plan.key, 0) + 1
        )
        self._merge_duplicates(plan.key)
        selected_track, selected_observation = accepted[0]
        self._plan_stages[plan.key] = "complete"
        return CacheSelection(
            selected_observation,
            selected_track.track_id,
            tuple(track.track_id for track, _ in accepted),
            tuple(rejected),
        )

    def discover(self, plan: BankPlan, observations: list[Observation]) -> tuple[int, ...]:
        if (self._plans.get(plan.key) != plan
                or self._plan_stages.get(plan.key) not in ("begun", "cache_failed")):
            raise ValueError("discovery does not belong to current bank visit")
        positives: list[Observation] = []
        for observation in observations:
            if observation.positive and not any(
                same_identity(existing, observation, plan.key.rate_hz)
                for existing in positives
            ):
                positives.append(observation)
        self._accepted_since_discovery[plan.key] = 0
        self._plan_stages[plan.key] = "complete"
        if not positives:
            return ()
        touched = []
        for observation in positives:
            match = self._matching_track(plan, observation)
            if match is None:
                tracker = Tracker(self._track_policy)
                tracker.begin(plan.key, plan.start_counter, plan.visit_index)
                if not tracker.update(
                    plan.key, plan.start_counter, plan.visit_index, observation, discovery=True
                ):
                    raise ValueError("positive discovery did not initialize track")
                match = Track(
                    self._next_track_id,
                    tracker,
                    observation,
                    plan.start_counter,
                    observation.margin,
                )
                self._next_track_id += 1
                self._tracks.setdefault(plan.key, []).append(match)
            else:
                if not match.tracker.update(
                    plan.key, plan.start_counter, plan.visit_index, observation, discovery=True
                ):
                    raise ValueError("positive discovery did not update track")
                match.last_observation = observation
                match.last_start_counter = plan.start_counter
                match.last_margin = observation.margin
            touched.append(match.track_id)
        self._merge_duplicates(plan.key)
        self._enforce_capacity(plan.key)
        live = {track.track_id for track in self._tracks.get(plan.key, [])}
        return tuple(track_id for track_id in touched if track_id in live)

    def _matching_track(self, plan: BankPlan, observation: Observation) -> Track | None:
        predictions = {
            item.track_id: item.prediction for item in plan.association_tracks
        }
        matches = []
        for track in self._tracks.get(plan.key, []):
            prediction = predictions.get(track.track_id)
            if prediction is not None:
                expected = Observation(
                    prediction.window,
                    prediction.epoch_samples,
                    prediction.cfo_hz,
                    1.0,
                    0.0,
                    True,
                    "predicted_verified",
                    prediction.scoring_cfo_hz,
                )
            elif track.last_start_counter == plan.start_counter:
                expected = track.last_observation
            else:
                continue
            if same_identity(expected, observation, plan.key.rate_hz):
                matches.append(track)
        return min(matches, key=lambda track: track.track_id) if matches else None

    def _merge_duplicates(self, key: Key) -> None:
        retained: list[Track] = []
        for track in sorted(self._tracks.get(key, []), key=lambda item: item.track_id):
            if any(
                existing.last_start_counter == track.last_start_counter
                and same_identity(existing.last_observation, track.last_observation, key.rate_hz)
                for existing in retained
            ):
                continue
            retained.append(track)
        self._tracks[key] = retained

    def _enforce_capacity(self, key: Key) -> None:
        tracks = self._tracks.get(key, [])
        while len(tracks) > self.maximum_tracks:
            victim = min(
                tracks,
                key=lambda track: (
                    track.last_start_counter,
                    track.last_margin,
                    -track.track_id,
                ),
            )
            tracks.remove(victim)
