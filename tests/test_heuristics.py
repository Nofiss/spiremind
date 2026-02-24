import pytest

from src.models.state import GameState, Card, Monster
from src.agents.heuristics import (
    parse_incoming_damage,
    lethal_action,
    block_action,
    potion_action,
    heuristic_action,
)


def make_state(**kwargs) -> GameState:
    return GameState(**kwargs)


def test_parse_incoming_damage_simple():
    state = make_state(
        monsters=[
            Monster(name="Cultist", current_hp=40, intent="8x2", block=0),
            Monster(name="Jaw Worm", current_hp=50, intent="10", block=0),
        ]
    )
    assert parse_incoming_damage(state) == 26


def test_lethal_action_single_target():
    state = make_state(
        available_commands=["play"],
        hand=[
            Card(
                name="Strike",
                cost=1,
                is_playable=True,
                has_target=True,
                type="ATTACK",
                damage=8,
            ),
        ],
        monsters=[Monster(name="Slime", current_hp=8, intent="UNKNOWN", block=0)],
        energy=1,
        ready_for_command=True,
        in_game=True,
    )
    action = lethal_action(state)
    assert action == "play 1 0"


def test_block_action_knapsack_prefers_max_block():
    state = make_state(
        available_commands=["play"],
        hand=[
            Card(
                name="Defend+",
                cost=2,
                is_playable=True,
                has_target=False,
                type="SKILL",
                block_value=12,
            ),
            Card(
                name="Defend",
                cost=1,
                is_playable=True,
                has_target=False,
                type="SKILL",
                block_value=8,
            ),
        ],
        monsters=[Monster(name="Worm", current_hp=30, intent="20", block=0)],
        energy=2,
        player_block=0,
        ready_for_command=True,
        in_game=True,
    )
    action = block_action(state)
    # Budget only allows one 2-cost card; best under budget is 12 block (card index 1)
    assert action == "play 1"


def test_potion_action_elite_turn1():
    state = make_state(
        available_commands=["use_potion"],
        potions=[{"name": "Strength Potion"}],
        room_type="ELITE",
        turn=1,
        hp=50,
        max_hp=80,
    )
    action = potion_action(state)
    assert action == "use_potion 0"


def test_heuristic_action_priority_lethal_over_potion():
    state = make_state(
        available_commands=["play", "use_potion"],
        hand=[
            Card(
                name="Strike",
                cost=1,
                is_playable=True,
                has_target=True,
                type="ATTACK",
                damage=10,
            ),
        ],
        monsters=[Monster(name="Slime", current_hp=10, intent="UNKNOWN", block=0)],
        energy=1,
        turn=1,
        room_type="ELITE",
        potions=[{"name": "Strength Potion"}],
        player_block=0,
        ready_for_command=True,
        in_game=True,
    )
    action = heuristic_action(state)
    # lethal should take precedence
    assert action == "play 1 0"
