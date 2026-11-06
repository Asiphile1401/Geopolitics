"""Pure-Python, framework-independent rules for the INF4001N geopolitics game.

The game state is a MongoDB-serialisable dictionary. No Flask request, global
MongoDB connection, or environment variables are needed to exercise the rules.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone


class GameRuleError(ValueError):
    """A requested action violates the exam's rules or the current turn state."""


def soldier_value(population: int) -> int:
    if population < 0:
        raise ValueError("Population must not be negative")
    for number, threshold in enumerate((5, 10, 25, 50, 75, 100, 125, 150), start=1):
        if population <= threshold * 1_000_000:
            return number
    return 9


def create_game(username: str, owner_id: str, chosen_country: str, catalog: dict,
                rng=None, npc_count: int = 3) -> dict:
    rng = rng or random.Random()
    if chosen_country not in catalog:
        raise GameRuleError("Select a country from the available list.")
    if len(catalog) < 10:
        raise GameRuleError("At least ten countries are required.")
    if not 1 <= npc_count <= 9:
        raise GameRuleError("The number of computer opponents must be between 1 and 9.")
    picks = [chosen_country] + rng.sample([n for n in catalog if n != chosen_country], 9)
    players = [{"id": "human", "name": username, "kind": "human", "alive": True}]
    players += [{"id": f"npc{i}", "name": f"Computer {i}", "kind": "npc", "alive": True}
                for i in range(1, npc_count + 1)]
    rng.shuffle(players)
    countries = {
        n: {
            "name": n, "population": catalog[n]["population"],
            "starting_soldiers": soldier_value(catalog[n]["population"]),
            "soldiers": soldier_value(catalog[n]["population"]), "owner": None
        } for n in picks
    }
    countries[chosen_country]["owner"] = "human"
    available = [n for n in picks if n != chosen_country]
    for player in players:
        if player["kind"] == "npc":
            choice = rng.choice(available)
            available.remove(choice)
            countries[choice]["owner"] = player["id"]
    game = {
        "title": "World Conquest", "owner_id": owner_id,
        "countries": countries, "players": players, "current_player": 0,
        "round": 1, "turns_taken": [], "phase": "action", "pending_reinforcements": 0,
        "attack": None, "npc_transfer_used": False,
        "status": "active", "winner": None, "events": [], "event_no": 0,
        "stats": {p['id']: {"attacks": 0, "dice_phases": 0, "conquests": 0,
                             "lost": 0, "defeated": 0} for p in players},
        "version": 1, "created_at": datetime.now(timezone.utc).isoformat()
    }
    engine = GameEngine(game, rng=rng)
    engine.log("game", f"New game: {chosen_country} belongs to {username}; nine other nations were drawn.")
    engine.log("turn", f"{engine.current_player['name']} was randomly selected to play first.")
    return game


class GameEngine:
    """Controls exactly one human or NPC move at a time."""

    def __init__(self, game: dict, rng=None, commentator=None):
        self.game = game
        self.rng = rng or random.Random()
        self.commentator = commentator

    @property
    def countries(self) -> dict:
        return self.game["countries"]

    @property
    def current_player(self) -> dict:
        return self.game["players"][self.game["current_player"]]

    @property
    def player_id(self) -> str:
        return self.current_player["id"]

    def owned(self, player_id=None) -> list[str]:
        pid = player_id or self.player_id
        return [n for n, c in self.countries.items() if c["owner"] == pid]

    def log(self, kind: str, message: str, **extra) -> None:
        self.game["event_no"] += 1
        self.game["events"].append({
            "id": self.game["event_no"], "kind": kind,
            "text": message, "round": self.game["round"],
            "time": datetime.now(timezone.utc).isoformat(), **extra
        })
        self.game["events"] = self.game["events"][-400:]

    def require_phase(self, *allowed) -> None:
        if self.game["status"] != "active":
            raise GameRuleError("This game is already finished.")
        if self.game["phase"] not in allowed:
            raise GameRuleError(f"Complete the {self.game['phase'].replace('_',' ')} stage first.")

    def require_human(self) -> None:
        if self.player_id != "human":
            raise GameRuleError("Only the computer can make this move right now.")

    def check_victory(self) -> bool:
        owners = {country["owner"] for country in self.countries.values()}
        if len(owners) != 1 or None in owners:
            return False
        winner = owners.pop()
        self.game["status"] = "finished"
        self.game["phase"] = "finished"
        self.game["attack"] = None
        self.game["winner"] = winner
        winner_name = next(p["name"] for p in self.game["players"] if p["id"] == winner)
        self.log("victory", f"🏆 {winner_name} conquered all ten countries and won the game!")
        return True

    def _refresh_players(self):
        for player in self.game["players"]:
            player["alive"] = bool(self.owned(player["id"]))

    def end_turn(self) -> None:
        """Rotate over eligible players; round 2 begins only when round 1 is complete."""
        if self.check_victory():
            return
        self._refresh_players()
        current = self.player_id
        if current not in self.game["turns_taken"]:
            self.game["turns_taken"].append(current)
        eligible = {p["id"] for p in self.game["players"] if p["alive"]}
        if eligible.issubset(set(self.game["turns_taken"])):
            self.game["round"] += 1
            self.game["turns_taken"] = []
            self.log("round", f"Round {self.game['round']} has started. Players receive 2 soldiers per country.")
        order = self.game["players"]
        start = self.game["current_player"]
        for move in range(1, len(order) + 1):
            idx = (start + move) % len(order)
            player = order[idx]
            if player["alive"] and player["id"] not in self.game["turns_taken"]:
                self.game["current_player"] = idx
                self.game["attack"] = None
                self.game["npc_transfer_used"] = False
                reinforcements = 2 * len(self.owned(player["id"])) if self.game["round"] >= 2 else 0
                self.game["pending_reinforcements"] = reinforcements
                self.game["phase"] = "reinforce" if reinforcements else "action"
                self.log("turn", f"{player['name']}'s turn begins" +
                         (f" — {reinforcements} reinforcements to assign." if reinforcements else "."))
                return
        raise AssertionError("No eligible player found in a game that has not been won")

    def reinforce(self, allocation: dict[str, int]):
        self.require_phase("reinforce")
        owned = set(self.owned())
        if not owned or not isinstance(allocation, dict):
            raise GameRuleError("Reinforcement destinations are invalid.")
        if any(name not in owned or type(qty) is not int or qty < 0
               for name, qty in allocation.items()):
            raise GameRuleError("Allocate only nonnegative whole numbers to your countries.")
        pending = self.game["pending_reinforcements"]
        if sum(allocation.values()) != pending:
            raise GameRuleError(f"You must allocate exactly {pending} soldiers.")
        for name, count in allocation.items():
            self.countries[name]["soldiers"] += count
        self.log("reinforcement", f"{self.current_player['name']} allocated {pending} reinforcements: " +
                 ", ".join(f"{n} +{v}" for n, v in allocation.items() if v))
        self.game["pending_reinforcements"] = 0
        self.game["phase"] = "action"

    def transfer(self, source: str, target: str, count: int):
        self.require_phase("action")
        if source not in self.countries or target not in self.countries or source == target:
            raise GameRuleError("Choose two different countries from the game board.")
        if self.countries[source]["owner"] != self.player_id or self.countries[target]["owner"] != self.player_id:
            raise GameRuleError("You may transfer soldiers only between your own countries.")
        if type(count) is not int or count < 1 or count >= self.countries[source]["soldiers"]:
            raise GameRuleError("Transfer at least one soldier and leave one behind.")
        self.countries[source]["soldiers"] -= count
        self.countries[target]["soldiers"] += count
        self.log("transfer", f"{self.current_player['name']} transferred {count} soldiers from {source} to {target}.")

    def begin_attack(self, source: str, target: str):
        self.require_phase("action")
        if source not in self.countries or target not in self.countries or source == target:
            raise GameRuleError("Choose two different countries on the board.")
        if self.countries[source]["owner"] != self.player_id:
            raise GameRuleError("The attacking country must belong to you.")
        if self.countries[target]["owner"] == self.player_id:
            raise GameRuleError("You cannot attack your own country.")
        if self.countries[source]["soldiers"] < 2:
            raise GameRuleError("A country must have at least 2 soldiers to attack.")
        self.game.setdefault('stats', {}).setdefault(self.player_id,
            {"attacks": 0, "dice_phases": 0, "conquests": 0, "lost": 0, "defeated": 0})['attacks'] += 1
        self.game["phase"] = "attacking"
        self.game["attack"] = {"source": source, "target": target, "phases": 0}
        self.log("attack", f"⚔️ {self.current_player['name']} attacks {target} from {source}.")

    def roll_phase(self):
        self.require_phase("attacking")
        attack = self.game["attack"]
        source, target = attack["source"], attack["target"]
        from_country, to_country = self.countries[source], self.countries[target]
        pairs = min(from_country["soldiers"] - 1, to_country["soldiers"])
        if pairs < 1:
            raise GameRuleError("Not enough soldiers remain to continue the attack.")
        attack_rolls = [self.rng.randint(1, 6) for _ in range(pairs)]
        defence_rolls = [self.rng.randint(1, 6) for _ in range(pairs)]
        attacker_losses = sum(a < d for a, d in zip(attack_rolls, defence_rolls))
        defender_losses = sum(a > d for a, d in zip(attack_rolls, defence_rolls))
        # A tie costs neither side a soldier. Dice are paired in their rolled order.
        from_country["soldiers"] -= attacker_losses
        to_country["soldiers"] -= defender_losses
        attack["phases"] += 1
        attacker_stat = self.game['stats'][self.player_id]
        attacker_stat['dice_phases'] += 1
        attacker_stat['lost'] += attacker_losses
        attacker_stat['defeated'] += defender_losses
        defending_owner = to_country['owner']
        if defending_owner is not None:
            self.game['stats'][defending_owner]['lost'] += defender_losses
            self.game['stats'][defending_owner]['defeated'] += attacker_losses
        summary = (f"{source} rolled {attack_rolls}; {target} rolled {defence_rolls}. "
                   f"Losses: {source} −{attacker_losses}, {target} −{defender_losses}.")
        if attacker_losses + defender_losses == 0:
            summary += " Tie: no soldiers lost."
        event = {
            "source": source, "target": target, "attacker_id": self.player_id,
            "defender_id": defending_owner, "attacker_rolls": attack_rolls,
            "defender_rolls": defence_rolls, "attacker_losses": attacker_losses,
            "defender_losses": defender_losses,
        }
        self.log("dice", summary, **event)
        if self.commentator is not None:
            try:
                commentary, mode = self.commentator.generate(event)
                if commentary:
                    self.log("commentary", commentary, mode=mode)
            except Exception:
                # A third-party AI outage should never break game rules or a user's turn.
                self.log("commentary", "Battle commentary is temporarily unavailable.", mode="unavailable")
        if to_country["soldiers"] == 0:
            old_owner = to_country["owner"]
            to_country["owner"] = self.player_id
            reward = max(2, to_country["starting_soldiers"] // 2)
            to_country["soldiers"] = reward
            self.game['stats'][self.player_id]['conquests'] += 1
            self.log("conquest", f"🎉 {self.current_player['name']} conquered {target} and "
                     f"placed {reward} awarded soldiers there.", previous_owner=old_owner)
            self._refresh_players()
            if old_owner and not self.owned(old_owner):
                self.log("elimination", f"{next(p['name'] for p in self.game['players'] if p['id'] == old_owner)} was eliminated.")
            if self.check_victory():
                return
            self.game["phase"] = "conquer_transfer"
            return
        if from_country["soldiers"] == 1:
            self.log("attack", f"{source} has one soldier remaining; the attack automatically ends.")
            self.end_turn()

    def stop_attack(self):
        self.require_phase("attacking")
        self.log("decision", f"{self.current_player['name']} stopped the attack and ended the turn.")
        self.end_turn()

    def finish_conquest(self, additional_soldiers: int):
        self.require_phase("conquer_transfer")
        source, target = self.game["attack"]["source"], self.game["attack"]["target"]
        if type(additional_soldiers) is not int or not 0 <= additional_soldiers < self.countries[source]["soldiers"]:
            raise GameRuleError("Enter 0 or more soldiers, leaving at least one at the source.")
        if additional_soldiers:
            self.countries[source]["soldiers"] -= additional_soldiers
            self.countries[target]["soldiers"] += additional_soldiers
            self.log("transfer", f"{self.current_player['name']} moved {additional_soldiers} extra soldiers "
                     f"from {source} to conquered {target}.")
        self.end_turn()

    def skip(self):
        self.require_phase("action")
        self.log("decision", f"{self.current_player['name']} skipped their turn.")
        self.end_turn()

    def _npc_reinforce(self):
        owned = self.owned()
        preferred = max(owned, key=lambda n: (self.countries[n]["soldiers"], self.countries[n]["starting_soldiers"]))
        troops = self.game["pending_reinforcements"]
        self.log("npc", f"{self.current_player['name']} reinforces {preferred} by {troops}: "
                 "concentrating forces improves the next attack's odds.")
        self.reinforce({preferred: troops})

    def _npc_transfer(self) -> bool:
        owned = self.owned()
        if len(owned) < 2:
            return False
        strongest = max(owned, key=lambda n: self.countries[n]["soldiers"])
        sources = [n for n in owned if n != strongest and self.countries[n]["soldiers"] > 1]
        if not sources:
            return False
        donor = max(sources, key=lambda n: self.countries[n]["soldiers"])
        move = self.countries[donor]["soldiers"] - 1
        self.log("npc", f"{self.current_player['name']} consolidates {move} soldiers from {donor} "
                 f"into {strongest}: the donor will retain one garrison.")
        self.transfer(donor, strongest, move)
        return True

    def _npc_best_attack(self):
        owned = [n for n in self.owned() if self.countries[n]["soldiers"] >= 2]
        enemies = [(n, c) for n, c in self.countries.items() if c["owner"] != self.player_id]
        if not owned or not enemies:
            return None
        target_owners = {p['id']: len(self.owned(p['id'])) for p in self.game['players']}
        choices = []
        for source in owned:
            available = self.countries[source]["soldiers"] - 1
            for target, country in enemies:
                ratio = available / country["soldiers"]
                if ratio >= 1.0:  # conserve soldiers if odds are distinctly unfavourable
                    owner = country['owner']
                    # Strategic priorities: claim all neutral nations; eliminate opponents
                    # who have one country left; then weaken the smallest rival.
                    if owner is None:
                        priority = (3, 0)
                    else:
                        count = target_owners[owner]
                        priority = (2 if count == 1 else 1, -count)
                    choices.append((priority, min(ratio, 10), country['starting_soldiers'],
                                    -country['soldiers'], source, target))
        if not choices:
            return None
        *_, source, target = max(choices)
        return source, target

    def npc_step(self):
        """Execute ONE visible NPC decision/phase. Repeated calls provide animated fast-forward."""
        if self.game["status"] != "active" or self.current_player["kind"] != "npc":
            raise GameRuleError("No NPC action is currently available.")
        phase = self.game["phase"]
        if phase == "reinforce":
            self._npc_reinforce()
        elif phase == "action":
            if not self.game["npc_transfer_used"]:
                self.game["npc_transfer_used"] = True
                if self._npc_transfer():
                    return
            decision = self._npc_best_attack()
            if decision is None:
                self.log("npc", f"{self.current_player['name']} skips: no available army has "
                         "at least as many attacking soldiers as a prospective defender.")
                self.skip()
            else:
                source, target = decision
                a = self.countries[source]["soldiers"] - 1
                d = self.countries[target]["soldiers"]
                self.log("npc", f"{self.current_player['name']} targets {target} from {source}: "
                         f"{a} soldiers can attack against {d} defending soldiers.")
                self.begin_attack(source, target)
        elif phase == "attacking":
            attack = self.game["attack"]
            a = self.countries[attack["source"]]["soldiers"] - 1
            d = self.countries[attack["target"]]["soldiers"]
            if attack["phases"] >= 40 or a < 0.8 * d:
                self.log("npc", f"{self.current_player['name']} stops attacking: "
                         "further losses outweigh the present chance of conquest.")
                self.stop_attack()
            else:
                self.log("npc", f"{self.current_player['name']} rolls again: {a} attacking "
                         f"soldiers versus {d} defenders remains a reasonable fight.")
                self.roll_phase()
        elif phase == "conquer_transfer":
            attack = self.game["attack"]
            source = attack["source"]
            # Transfer up to half the free garrison to secure a freshly conquered nation.
            extra = (self.countries[source]["soldiers"] - 1) // 2
            self.log("npc", f"{self.current_player['name']} assigns {extra} additional "
                     f"soldiers to its new territory {attack['target']} for defence.")
            self.finish_conquest(extra)
        else:
            raise GameRuleError("Unexpected NPC turn phase.")

    def summary(self) -> dict:
        """Return only game information visitors may see."""
        state = {key: self.game.get(key) for key in (
            "title", "countries", "players", "current_player", "round",
            "phase", "pending_reinforcements", "attack", "status", "winner",
            "created_at", "version")}
        state["id"] = str(self.game.get("_id", ""))
        state["events"] = self.game["events"][-100:]
        state["turn_name"] = self.current_player["name"]
        state["is_human_turn"] = self.player_id == "human"
        state['statistics'] = {
            player['id']: {
                **self.game.get('stats', {}).get(player['id'], {}),
                'territories': len(self.owned(player['id'])),
                'soldiers': sum(self.countries[n]['soldiers'] for n in self.owned(player['id']))
            } for player in self.game['players']
        }
        return state
