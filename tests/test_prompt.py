from src.models.state import GameState, Card, Monster
from src.utils.prompt import build_combat_prompt


def test_build_prompt_contains_sections():
    state = GameState(
        current_hp=70,
        energy=3,
        hand=[
            Card(
                name="Strike",
                cost=1,
                is_playable=True,
                has_target=True,
                type="ATTACK",
                damage=6,
            )
        ],
        monsters=[Monster(name="Cultist", current_hp=40, intent="UNKNOWN")],
        available_commands=["play", "end"],
        map_choices=["1:2", "2:2"],
        deck=["Strike", "Defend", "Bash"],
        reward_cards=[
            Card(
                name="Heavy Blade",
                cost=2,
                is_playable=True,
                has_target=True,
                type="ATTACK",
                damage=14,
            )
        ],
    )
    prompt = build_combat_prompt(state)
    assert "--- SLAY THE SPIRE STATE ---" in prompt
    assert "HERO:" in prompt
    assert "ENEMIES:" in prompt
    assert "HAND:" in prompt
    assert "MAP_CHOICES:" in prompt
    assert "DECK:" in prompt
    assert "CARD_REWARD_OPTIONS:" in prompt
    assert "VALID COMMANDS:" in prompt
    assert (
        "Thought:" not in prompt
    )  # instruction is to write Thought, not hardcoded content
