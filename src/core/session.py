from typing import List, Set


class SessionManager:
    """
    Lightweight run/session memory for long-term planning.
    Tracks recent actions (per turn), potion usage, and elites defeated.
    """

    def __init__(self):
        self.turn_index: int = 0
        self.cards_played_this_turn: List[str] = []
        self.commands_this_turn: List[str] = []
        self.last_turn_cards: List[str] = []
        self.last_turn_commands: List[str] = []
        self.elites_defeated: Set[str] = set()
        self.potions_used: int = 0
        self.last_encounter_monsters: List[str] = []
        self.last_room_type: str = "UNKNOWN"

    def record_command(self, cmd: str):
        if not cmd:
            return
        self.commands_this_turn.append(cmd)

    def record_play(self, card_name: str):
        if not card_name:
            return
        self.cards_played_this_turn.append(str(card_name))

    def record_potion_use(self):
        self.potions_used += 1

    def start_new_turn(self):
        self.turn_index += 1
        self.last_turn_cards = list(self.cards_played_this_turn)
        self.last_turn_commands = list(self.commands_this_turn)
        self.cards_played_this_turn.clear()
        self.commands_this_turn.clear()

    def update_room_type(self, room_type: str):
        if room_type:
            self.last_room_type = str(room_type).upper()

    def observe_monsters(self, names: List[str]):
        # Keep last seen monster names (alive or current encounter)
        self.last_encounter_monsters = [str(n) for n in names]

    def finalize_combat_if_ended(self, was_in_game: bool, now_in_game: bool):
        if was_in_game and not now_in_game:
            # Combat ended; if this was an elite room, record defeated elite(s)
            rt = self.last_room_type
            if "ELITE" in rt:
                for n in self.last_encounter_monsters:
                    self.elites_defeated.add(n)
