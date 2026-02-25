from __future__ import annotations

from dataclasses import dataclass
from typing import List

import random


@dataclass
class SimCard:
    name: str
    cost: int
    damage: int
    block: int
    has_target: bool = True
    is_playable: bool = True


@dataclass
class SimMonster:
    name: str
    current_hp: int
    max_hp: int
    intent_damage: int
    block: int = 0
    is_gone: bool = False


@dataclass
class SimState:
    available_commands: List[str]
    ready_for_command: bool
    in_game: bool
    hand: List[SimCard]
    monsters: List[SimMonster]
    energy: int
    hp: int
    max_hp: int
    player_block: int
    turn: int


class SimGame:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.turn = 1
        self.player_hp = 70
        self.player_max_hp = 70
        self.player_block = 0
        self.energy = 3
        self.monsters = self._spawn_monsters()
        self.hand = self._draw_hand()
        self.in_game = True
        self._combat_start_hp = self.player_hp
        self._combat_start_max_hp = self.player_max_hp

    def reset(self) -> SimState:
        self.turn = 1
        self.player_hp = 70
        self.player_max_hp = 70
        self.player_block = 0
        self.energy = 3
        self.monsters = self._spawn_monsters()
        self.hand = self._draw_hand()
        self.in_game = True
        self._combat_start_hp = self.player_hp
        self._combat_start_max_hp = self.player_max_hp
        return self._build_state()

    def _spawn_monsters(self) -> List[SimMonster]:
        count = self.rng.randint(1, 3)
        monsters: List[SimMonster] = []
        for i in range(count):
            hp = self.rng.randint(18, 45)
            intent = self.rng.randint(4, 12)
            monsters.append(
                SimMonster(
                    name=f"M{i}",
                    current_hp=hp,
                    max_hp=hp,
                    intent_damage=intent,
                )
            )
        return monsters

    def _draw_hand(self) -> List[SimCard]:
        hand: List[SimCard] = []
        for i in range(5):
            if self.rng.random() < 0.6:
                dmg = self.rng.randint(4, 12)
                hand.append(
                    SimCard(
                        name=f"Strike{i}", cost=1, damage=dmg, block=0, has_target=True
                    )
                )
            else:
                blk = self.rng.randint(4, 12)
                hand.append(
                    SimCard(
                        name=f"Defend{i}", cost=1, damage=0, block=blk, has_target=False
                    )
                )
        return hand

    def _build_state(self) -> SimState:
        return SimState(
            available_commands=["play", "end", "wait"],
            ready_for_command=True,
            in_game=self.in_game,
            hand=list(self.hand),
            monsters=list(self.monsters),
            energy=self.energy,
            hp=self.player_hp,
            max_hp=self.player_max_hp,
            player_block=self.player_block,
            turn=self.turn,
        )

    def step(self, command: str) -> tuple[SimState, float, bool, bool]:
        reward = 0.0
        if not self.in_game:
            return self._build_state(), reward, True, False

        parts = (command or "").split()
        if not parts:
            reward -= 0.1
            return self._build_state(), reward, False, False

        base = parts[0].lower()
        if base == "play":
            reward += self._handle_play(parts)
        elif base == "end":
            reward += self._handle_end_turn()
        elif base == "wait":
            reward -= 0.05
        else:
            reward -= 0.1

        terminated = self.player_hp <= 0 or self._all_monsters_dead()
        if terminated:
            self.in_game = False
            if self.player_hp > 0:
                reward += 100.0
                hp_loss = max(0, self._combat_start_hp - self.player_hp)
                if self._combat_start_max_hp > 0:
                    reward += 1.0 - (float(hp_loss) / float(self._combat_start_max_hp))
            else:
                reward -= 100.0
        return self._build_state(), reward, terminated, False

    def _handle_play(self, parts: List[str]) -> float:
        if len(parts) < 2:
            return -0.1
        try:
            idx1 = int(parts[1])
        except Exception:
            return -0.1
        if idx1 < 1 or idx1 > len(self.hand):
            return -0.1

        card = self.hand[idx1 - 1]
        if not card.is_playable or card.cost > self.energy:
            return -0.1

        if card.has_target:
            if len(parts) < 3:
                return -0.1
            try:
                t = int(parts[2])
            except Exception:
                return -0.1
            if t < 0 or t >= len(self.monsters):
                return -0.1
            m = self.monsters[t]
            if m.is_gone or m.current_hp <= 0:
                return -0.1
            dmg = max(0, card.damage - m.block)
            m.block = max(0, m.block - card.damage)
            m.current_hp = max(0, m.current_hp - dmg)
            if m.current_hp == 0:
                m.is_gone = True
            self.energy -= card.cost
            return 0.0

        self.player_block += card.block
        self.energy -= card.cost
        return 0.0

    def _handle_end_turn(self) -> float:
        incoming = sum(
            m.intent_damage for m in self.monsters if not m.is_gone and m.current_hp > 0
        )
        mitigated = min(self.player_block, incoming)
        dmg = max(0, incoming - self.player_block)
        self.player_hp = max(0, self.player_hp - dmg)
        self.player_block = 0
        self.turn += 1
        self.energy = 3
        self.hand = self._draw_hand()
        return 0.0

    def _all_monsters_dead(self) -> bool:
        return all(m.is_gone or m.current_hp <= 0 for m in self.monsters)
