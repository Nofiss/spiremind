from typing import List
from models.state import GameState


def build_combat_prompt(state: GameState) -> str:
    monsters_info: List[str] = []
    for i, m in enumerate(state.monsters):
        if not m.is_gone:
            monsters_info.append(f"{i}: {m.name}({m.current_hp}HP, {m.intent})")

    hand_info: List[str] = []
    for i, card in enumerate(state.hand):
        idx = i + 1
        target_marker = "[TARGET]" if card.has_target else ""
        cost = f"({card.cost}E)"
        hand_info.append(f"{idx}: {card.name}{cost}{target_marker}")

    deck_counts = {}
    for name in state.deck or []:
        deck_counts[name] = deck_counts.get(name, 0) + 1
    deck_str = (
        ", ".join([f"{n} x{c}" for n, c in deck_counts.items()])
        if deck_counts
        else "(empty)"
    )

    reward_strs = []
    for rc in state.reward_cards or []:
        reward_strs.append(
            rc.name if hasattr(rc, "name") else str(getattr(rc, "name", "UNKNOWN"))
        )
    reward_str = ", ".join(reward_strs) if reward_strs else "(none)"

    prompt = (
        f"--- SLAY THE SPIRE STATE ---\n"
        f"HERO: {state.hp} HP, {state.energy} Energy.\n"
        f"ENEMIES: {', '.join(monsters_info)}\n"
        f"HAND: {', '.join(hand_info)}\n"
        f"MAP_CHOICES: {state.map_choices}\n"
        f"DECK: {deck_str}\n"
        f"CARD_REWARD_OPTIONS: {reward_str}\n"
        f"VALID COMMANDS: {state.available_commands}\n"
        f"----------------------------\n"
        f"GOAL: Win the fight. Dont die.\n"
        f"INSTRUCTIONS:\n"
        f"1. To play a card, reply: 'play CARD_INDEX [TARGET_INDEX]'.\n"
        f"   Example: 'play 1 0' (Play card 1 on enemy 0). Cards are 1-based, targets are 0-based.\n"
        f"   If card has no [TARGET], 'play CARD_INDEX' is enough.\n"
        f"2. To end turn, reply: 'end'.\n"
        f"3. When choosing a reward (card_reward), reply 'choose INDEX'. Consider deck synergies with the current deck.\n"
        f"4. First write one line 'Thought: <brief reasoning>'. Then one line 'Action: <command>' with ONLY the final command."
    )
    return prompt
