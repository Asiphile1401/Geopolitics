import copy
import random

import pytest

from game.engine import GameEngine, GameRuleError, create_game, soldier_value
from game.commentary import BattleCommentator


@pytest.fixture
def catalog():
    populations = (900_000, 5_000_000, 7_000_000, 12_000_000, 32_000_000,
                   70_000_000, 95_000_000, 120_000_000, 140_000_000, 190_000_000,
                   250_000_000, 310_000_000)
    return {f'Nation {i}': {'name': f'Nation {i}', 'population': population}
            for i, population in enumerate(populations)}


@pytest.fixture
def game(catalog):
    result = create_game('Tester', 'user-1', 'Nation 0', catalog, rng=random.Random(10))
    # Pin starting turn order for tests that depend on the human going first.
    result['players'].sort(key=lambda p: (p['id'] != 'human', p['id']))
    result['current_player'] = 0
    return result


class FixedRNG:
    def __init__(self, rolls):
        self.rolls = list(rolls)

    def randint(self, low, high):
        return self.rolls.pop(0)


@pytest.mark.parametrize(('population', 'expected'), [
    (0, 1), (5_000_000, 1), (5_000_001, 2), (10_000_000, 2),
    (10_000_001, 3), (25_000_000, 3), (25_000_001, 4),
    (50_000_000, 4), (75_000_000, 5), (100_000_000, 6),
    (125_000_000, 7), (150_000_000, 8), (150_000_001, 9)
])
def test_soldier_bands(population, expected):
    assert soldier_value(population) == expected


def test_random_board_and_initial_owners(catalog):
    game = create_game('T', 'abc', 'Nation 0', catalog, rng=random.Random(2))
    assert len(game['countries']) == 10
    assert game['countries']['Nation 0']['owner'] == 'human'
    assert len([c for c in game['countries'].values() if c['owner'] is None]) == 6
    assert len({p['id'] for p in game['players']}) == 4
    assert game['round'] == 1
    assert game['phase'] == 'action'
    assert game['pending_reinforcements'] == 0


def test_first_round_finishes_only_after_every_turn(game):
    engine = GameEngine(game)
    for _ in range(3):
        engine.skip()
        assert game['round'] == 1
        assert game['pending_reinforcements'] == 0
    engine.skip()
    assert game['round'] == 2
    assert game['phase'] == 'reinforce'
    assert game['pending_reinforcements'] == 2


def test_reinforcement_allocation_is_exact_and_can_be_split(game):
    countries = game['countries']
    other = next(name for name, c in countries.items() if c['owner'] is None)
    countries[other]['owner'] = 'human'
    game['phase'] = 'reinforce'
    game['pending_reinforcements'] = 4
    eng = GameEngine(game)
    original = {n: c['soldiers'] for n, c in countries.items()}
    with pytest.raises(GameRuleError):
        eng.reinforce({'Nation 0': 3})
    with pytest.raises(GameRuleError):
        eng.reinforce({'Nation 0': 4, 'Nation 1': 1})
    eng.reinforce({'Nation 0': 1, other: 3})
    assert countries['Nation 0']['soldiers'] == original['Nation 0'] + 1
    assert countries[other]['soldiers'] == original[other] + 3
    assert game['phase'] == 'action'


def test_transfers_keep_one_soldier_and_are_repeatable(game):
    countries = game['countries']
    first = next(name for name, c in countries.items() if c['owner'] is None)
    countries[first]['owner'] = 'human'
    countries['Nation 0']['soldiers'] = 8
    eng = GameEngine(game)
    with pytest.raises(GameRuleError):
        eng.transfer('Nation 0', first, 8)
    with pytest.raises(GameRuleError):
        eng.transfer('Nation 0', 'Nation 0', 1)
    eng.transfer('Nation 0', first, 4)
    eng.transfer(first, 'Nation 0', 2)
    assert countries['Nation 0']['soldiers'] == 6
    assert game['phase'] == 'action'


def test_ties_do_not_kill_and_dice_are_matched_in_rolled_order(game):
    countries = game['countries']
    countries['Nation 0']['soldiers'] = 4
    target = next(name for name, c in countries.items() if c['owner'] is None)
    countries[target]['soldiers'] = 2
    eng = GameEngine(game, rng=FixedRNG([2, 6, 2, 1]))
    eng.begin_attack('Nation 0', target)
    eng.roll_phase()
    assert countries['Nation 0']['soldiers'] == 4
    assert countries[target]['soldiers'] == 1
    dice = [e for e in game['events'] if e['kind'] == 'dice'][-1]
    assert dice['attacker_rolls'] == [2, 6]
    assert dice['defender_rolls'] == [2, 1]
    assert dice['attacker_losses'] == 0
    assert dice['defender_losses'] == 1
    assert game['phase'] == 'attacking'


def test_all_dice_roll_when_armies_are_large(game):
    game['countries']['Nation 0']['soldiers'] = 10
    target = next(name for name, c in game['countries'].items() if c['owner'] is None)
    game['countries'][target]['soldiers'] = 7
    eng = GameEngine(game, rng=FixedRNG([3] * 14))
    eng.begin_attack('Nation 0', target)
    eng.roll_phase()
    dice = [e for e in game['events'] if e['kind'] == 'dice'][-1]
    assert len(dice['attacker_rolls']) == 7
    assert len(dice['defender_rolls']) == 7
    assert game['countries']['Nation 0']['soldiers'] == 10
    assert game['countries'][target]['soldiers'] == 7


def test_conquest_bonus_half_soldier_value_and_occupation(game):
    target = next(n for n, c in game['countries'].items()
                  if c['owner'] is None and c['starting_soldiers'] >= 5)
    game['countries']['Nation 0']['soldiers'] = 6
    game['countries'][target]['soldiers'] = 1
    initial_value = game['countries'][target]['starting_soldiers']
    eng = GameEngine(game, rng=FixedRNG([6, 1]))
    eng.begin_attack('Nation 0', target)
    eng.roll_phase()
    assert game['phase'] == 'conquer_transfer'
    assert game['countries'][target]['owner'] == 'human'
    assert game['countries'][target]['soldiers'] == max(2, initial_value // 2)
    with pytest.raises(GameRuleError):
        eng.finish_conquest(6)
    eng.finish_conquest(3)
    assert game['countries']['Nation 0']['soldiers'] == 3
    assert game['countries'][target]['soldiers'] == max(2, initial_value // 2) + 3
    assert game['turns_taken'] == ['human']


def test_attack_is_one_per_turn_and_stop_advances(game):
    game['countries']['Nation 0']['soldiers'] = 10
    target = next(n for n, c in game['countries'].items() if c['owner'] is None)
    eng = GameEngine(game)
    eng.begin_attack('Nation 0', target)
    with pytest.raises(GameRuleError):
        eng.begin_attack('Nation 0', target)
    with pytest.raises(GameRuleError):
        eng.transfer('Nation 0', target, 2)
    eng.stop_attack()
    assert game['current_player'] == 1


def test_attacker_with_one_soldier_automatically_ends_turn(game):
    game['countries']['Nation 0']['soldiers'] = 2
    target = next(n for n, c in game['countries'].items() if c['owner'] is None)
    game['countries'][target]['soldiers'] = 4
    eng = GameEngine(game, rng=FixedRNG([1, 6]))
    eng.begin_attack('Nation 0', target)
    eng.roll_phase()
    assert game['countries']['Nation 0']['soldiers'] == 1
    assert game['current_player'] == 1
    assert game['countries'][target]['owner'] is None


def test_no_premature_victory_while_neutral_territory_exists(game):
    for name, country in game['countries'].items():
        country['owner'] = 'human'
    last_name = next(iter(game['countries']))
    game['countries'][last_name]['owner'] = None
    engine = GameEngine(game)
    assert not engine.check_victory()
    assert game['status'] == 'active'
    game['countries'][last_name]['owner'] = 'human'
    assert engine.check_victory()
    assert game['status'] == 'finished'
    assert game['winner'] == 'human'


def test_eliminated_players_do_not_receive_turns(game):
    game['players'].sort(key=lambda p: (p['id'] != 'human', p['id']))
    doomed = game['players'][1]['id']
    for country in game['countries'].values():
        if country['owner'] == doomed:
            country['owner'] = None
    eng = GameEngine(game)
    eng.skip()
    assert game['players'][game['current_player']]['id'] != doomed


def test_npc_each_decision_is_separate_and_explained(game):
    game['current_player'] = 1
    npc = game['players'][1]['id']
    owned = next(n for n,c in game['countries'].items() if c['owner'] == npc)
    game['countries'][owned]['soldiers'] = 10
    game['phase'] = 'reinforce'
    game['pending_reinforcements'] = 2
    eng = GameEngine(game, rng=FixedRNG([6]*40))
    eng.npc_step()
    assert game['phase'] == 'action'
    assert any(e['kind'] == 'npc' for e in game['events'])
    eng.npc_step()
    assert game['phase'] == 'attacking'
    assert any('targets' in e['text'] for e in game['events'] if e['kind'] == 'npc')
    eng.npc_step()
    assert any(e['kind'] == 'dice' for e in game['events'])


def test_offline_commentary_provenance():
    speaker = BattleCommentator(api_url='https://YOUR_AI_PROVIDER.example/v1/chat/completions',
                                api_key='YOUR_API_KEY', model='YOUR_CHAT_MODEL')
    comment, mode = speaker.generate({'source': 'A', 'target': 'B', 'attacker_losses': 0,
                                      'defender_losses': 0, 'attacker_rolls':[4], 'defender_rolls':[4]})
    assert mode == 'offline'
    assert 'stalemate' in comment
