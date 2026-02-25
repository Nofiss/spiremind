from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config import BotConfig


@dataclass
class RewardEvent:
    reward: float
    done: bool
    reason: str


class RewardTracker:
    def __init__(self):
        self._combat_active = False
        self._combat_start_hp: Optional[int] = None
        self._combat_start_max_hp: Optional[int] = None
        self._last_fight_key: Optional[tuple[int, int, str]] = None
        self._last_run_end_key: Optional[tuple[int, int, Optional[bool], int]] = None
        self._last_act = 0
        self._last_floor = 0

    def update(self, prev_state, state) -> Optional[RewardEvent]:
        if not state:
            return None

        # Run end (victory or defeat)
        if str(getattr(state, "screen_type", "")).upper() == "GAME_OVER":
            victory = getattr(state, "victory", None)
            if victory is None:
                return None
            key = (
                int(getattr(state, "act", 0) or 0),
                int(getattr(state, "floor", 0) or 0),
                victory,
                int(getattr(state, "score", 0) or 0),
            )
            if key == self._last_run_end_key:
                return None
            self._last_run_end_key = key
            return RewardEvent(
                reward=BotConfig.REWARD_RUN_WIN
                if victory
                else BotConfig.REWARD_RUN_LOSS,
                done=True,
                reason="run_end",
            )

        # Act completion reward (detect act increment)
        try:
            act = int(getattr(state, "act", 0) or 0)
        except Exception:
            act = 0
        try:
            floor = int(getattr(state, "floor", 0) or 0)
        except Exception:
            floor = 0
        if act and (
            act < self._last_act or (act == self._last_act and floor < self._last_floor)
        ):
            self._last_act = 0
            self._last_floor = 0
            self._last_fight_key = None
            self._last_run_end_key = None
        if act and act > self._last_act:
            completed_act = act - 1
            if completed_act > 0:
                reward = self._act_reward(completed_act)
                self._last_act = act
                return RewardEvent(reward=reward, done=False, reason="act_complete")
        self._last_act = max(self._last_act, act)
        self._last_floor = max(self._last_floor, floor)

        screen_type = str(getattr(state, "screen_type", "")).upper()
        room_phase = str(getattr(state, "room_phase", "")).upper()

        # Track combat start
        if room_phase == "COMBAT" and not self._combat_active:
            self._combat_active = True
            try:
                self._combat_start_hp = int(getattr(state, "hp", 0) or 0)
                self._combat_start_max_hp = int(getattr(state, "max_hp", 0) or 0)
            except Exception:
                self._combat_start_hp = None
                self._combat_start_max_hp = None

        # Fight end reward (combat rewards screen)
        if screen_type == "COMBAT_REWARD" and room_phase == "COMPLETE":
            key = (
                int(getattr(state, "act", 0) or 0),
                int(getattr(state, "floor", 0) or 0),
                screen_type,
            )
            if key != self._last_fight_key:
                self._last_fight_key = key
                reward = BotConfig.REWARD_FIGHT_WIN_BASE
                if self._combat_start_hp is not None and self._combat_start_max_hp:
                    hp_loss = max(
                        0, self._combat_start_hp - int(getattr(state, "hp", 0) or 0)
                    )
                    reward -= (
                        float(hp_loss)
                        / float(max(1, self._combat_start_max_hp))
                        * BotConfig.REWARD_FIGHT_HP_LOSS_SCALE
                    )
                reward = max(
                    BotConfig.REWARD_FIGHT_MIN,
                    min(BotConfig.REWARD_FIGHT_MAX, reward),
                )
                self._combat_active = False
                self._combat_start_hp = None
                self._combat_start_max_hp = None
                return RewardEvent(reward=reward, done=False, reason="fight_end")

        return None

    @staticmethod
    def _act_reward(act_num: int) -> float:
        if act_num <= 1:
            return BotConfig.REWARD_ACT1
        if act_num == 2:
            return BotConfig.REWARD_ACT2
        return BotConfig.REWARD_ACT3
