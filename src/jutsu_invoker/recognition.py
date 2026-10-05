"""Timestamp-based acceptance and compact recipes, independent of inference."""
from __future__ import annotations

from dataclasses import dataclass
import itertools
import json
import math
from pathlib import Path

TOKENS = {"monkey": "Q", "tiger": "W", "horse": "E"}


@dataclass(frozen=True)
class Observation:
    timestamp_ms: float
    sign: str
    score: float
    margin: float
    fresh_visual: bool = True


@dataclass(frozen=True)
class Thresholds:
    enter_score: float = 0.8
    class_margin: float = 0.15
    element_stable_ms: float = 50
    confirmation_stable_ms: float = 66
    element_observations: int = 3
    confirmation_observations: int = 4
    timeout_ms: float = 1200
    max_age_ms: float = 100
    max_gap_ms: float = 100
    release_ms: float = 50
    monkey_enter_score: float | None = None
    monkey_stable_ms: float | None = None
    monkey_observations: int | None = None
    tiger_enter_score: float | None = None
    tiger_stable_ms: float | None = None
    tiger_observations: int | None = None
    confirmation_hold_score: float | None = None
    confirmation_dropout_ms: float = 0

    def score_for(self, sign):
        if sign == 'tiger' and self.tiger_enter_score is not None:
            return self.tiger_enter_score
        return self.monkey_enter_score if sign == 'monkey' and self.monkey_enter_score is not None else self.enter_score

    def stability_for(self, sign):
        if sign == 'snake':
            return self.confirmation_stable_ms, self.confirmation_observations
        if sign == 'monkey':
            return (self.monkey_stable_ms if self.monkey_stable_ms is not None else self.element_stable_ms,
                    self.monkey_observations if self.monkey_observations is not None else self.element_observations)
        if sign == 'tiger':
            return (self.tiger_stable_ms if self.tiger_stable_ms is not None else self.element_stable_ms,
                    self.tiger_observations if self.tiger_observations is not None else self.element_observations)
        return self.element_stable_ms, self.element_observations


class Trainer:
    def __init__(self, recipes: Path, thresholds: Thresholds | None = None):
        self.thresholds = thresholds or Thresholds()
        spec = json.loads(recipes.read_text())
        self.spells = {tuple(sorted(spell["orbs"])): spell for spell in spec["spells"]}
        if len(self.spells) != 10 or set(self.spells) != set(itertools.combinations_with_replacement("EQW", 3)):
            raise ValueError("Recipe spec must contain all ten orb multisets")
        self.pending: list[str] = []
        self.last_token_ms: float | None = None
        self.last_activity_ms: float | None = None
        self.last_timestamp_ms: float | None = None
        self.latched: str | None = None
        self._clear_candidate()
        self.release_start: float | None = None
        self.release_count = 0

    def _clear_candidate(self) -> None:
        self.candidate: str | None = None
        self.candidate_start = 0.0
        self.candidate_count = 0
        self.candidate_last_reliable_ms: float | None = None
        self.candidate_weak_count = 0

    def cancel(self, reason: str = "manual_cancel") -> dict:
        self.pending.clear()
        self.last_token_ms = None
        self.last_activity_ms = None
        self.latched = None
        self.release_start = None
        self.release_count = 0
        self._clear_candidate()
        return {"type": "cancelled", "reason": reason, "pending": []}

    def miss(self, now_ms: float, reason: str) -> list[dict]:
        """Discard pose evidence, not accepted selectors, during brief video jitter."""
        self._clear_candidate()
        self.release_start = None
        self.release_count = 0
        if self.last_activity_ms is not None and now_ms - self.last_activity_ms > self.thresholds.timeout_ms:
            held = self.latched
            event = self.cancel("recipe_timeout")
            self.latched = held
            return [event]
        return [{"type": "rejected", "reason": reason, "pending": self.pending.copy()}]

    def update(self, observation: Observation, now_ms: float) -> list[dict]:
        t, th = observation.timestamp_ms, self.thresholds
        if not isinstance(observation.fresh_visual, bool):
            return [self.cancel("invalid_observation")]
        if not all(math.isfinite(v) for v in (t, now_ms, observation.score, observation.margin)):
            return [self.cancel("invalid_observation")]
        if not (0 <= observation.score <= 1 and 0 <= observation.margin <= 1):
            return [self.cancel("invalid_observation")]
        if t > now_ms or now_ms - t > th.max_age_ms or not observation.fresh_visual:
            return self.miss(now_ms, "stale_or_nonvisual")
        if self.last_timestamp_ms is not None and t <= self.last_timestamp_ms:
            # A duplicate frame must never add evidence, release a latch, or refresh a recipe.
            if self.last_activity_ms is not None and now_ms - self.last_activity_ms > th.timeout_ms:
                return self.miss(now_ms, "non_increasing_timestamp")
            return [{"type": "rejected", "reason": "non_increasing_timestamp", "pending": self.pending.copy()}]
        events = []
        if self.last_timestamp_ms is not None and t - self.last_timestamp_ms > th.max_gap_ms:
            events.extend(self.miss(now_ms, "observation_gap"))
        self.last_timestamp_ms = t
        if self.last_activity_ms is not None and now_ms - self.last_activity_ms > th.timeout_ms:
            held = self.latched
            events.append(self.cancel("recipe_timeout"))
            self.latched = held
        supported = observation.sign in (*TOKENS, "snake")
        reliable = supported and observation.score >= th.score_for(observation.sign) and observation.margin >= th.class_margin
        if not reliable:
            # One weak SAME-class image may bridge a short snake confidence dip.
            # It adds no evidence and cannot confirm; stale/unknown/other-class
            # images and ambiguous margins still discard the candidate.
            bridge = (observation.sign == self.candidate == 'snake' and bool(self.pending)
                      and th.confirmation_hold_score is not None
                      and observation.score >= th.confirmation_hold_score
                      and observation.margin >= th.class_margin
                      and self.candidate_weak_count == 0
                      and self.candidate_last_reliable_ms is not None
                      and t-self.candidate_last_reliable_ms <= th.confirmation_dropout_ms)
            if bridge:
                self.candidate_weak_count += 1
            else:
                self._clear_candidate()
            # Low-margin / low-score supported signs may just be tracking noise.
            # Only explicit unknown/transition/other signs can release a held sign.
            if not supported:
                if self.release_start is None:
                    self.release_start = t
                self.release_count += 1
                if self.release_count >= 2 and t - self.release_start >= th.release_ms:
                    self.latched = None
            else:
                self.release_start = None
                self.release_count = 0
            reason = "unsupported_or_transition" if not supported else "low_confidence_or_margin"
            return events + [{"type": "rejected", "reason": reason, "pending": self.pending.copy()}]
        self.release_start = None
        self.release_count = 0
        # A visible selected pose keeps the recipe alive. Unknown frames preserve it
        # for timeout_ms; they never renew the deadline or count as a new selector.
        if TOKENS.get(observation.sign) in self.pending:
            self.last_activity_ms = t
        if observation.sign == self.latched:
            self._clear_candidate()
            return events
        if self.candidate_weak_count and self.candidate_last_reliable_ms is not None and t-self.candidate_last_reliable_ms > th.confirmation_dropout_ms:
            self._clear_candidate()
        if observation.sign != self.candidate:
            self._clear_candidate()
            self.candidate = observation.sign
            self.candidate_start = t
            self.candidate_count = 0
        self.candidate_count += 1
        self.candidate_last_reliable_ms = t
        confirm = observation.sign == "snake"
        duration, count = th.stability_for(observation.sign)
        if t - self.candidate_start < duration or self.candidate_count < count:
            return events
        self.latched = observation.sign
        self._clear_candidate()
        if confirm:
            if not self.pending:
                return events + [{"type": "rejected", "reason": "confirmation_without_recipe", "pending": []}]
            if len(self.pending) == 1:
                orbs = self.pending[0] * 3
            elif len(self.pending) == 2:
                orbs = self.pending[0] * 2 + self.pending[1]
            else:
                orbs = "QWE"
            spell = self.spells[tuple(sorted(orbs))]
            sequence = self.pending.copy() + ["R"]
            self.pending.clear()
            self.last_token_ms = None
            self.last_activity_ms = None
            return events + [{"type": "recipe", "spell": spell["name"], "orbs": orbs,
                              "sequence": sequence, "timestamp_ms": t, "output": "local_trainer"}]
        token = TOKENS[observation.sign]
        if token in self.pending:
            return events + [{"type": "rejected", "reason": "selector_already_selected",
                              "pending": self.pending.copy()}]
        self.pending.append(token)
        self.last_token_ms = t
        self.last_activity_ms = t
        return events + [{"type": "accepted", "sign": observation.sign, "token": token,
                          "pending": self.pending.copy(), "timestamp_ms": t}]
