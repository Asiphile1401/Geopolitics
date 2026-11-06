"""End-to-end rules tests that drive AI and human turns without Flask/MongoDB."""
import random

import pytest

from game.catalog import COUNTRY_DATA
from game.engine import GameEngine, create_game


def simulate(seed, max_steps=1200):
    rng = random.Random(seed)
    game = create_game('Tester', 'owner-1', 'South Africa', COUNTRY_DATA, rng=rng)
    engine = GameEngine(game, rng=rng)
    for step in range(max_steps):
        if game['status'] != 'active':
            return game, step
        assert len(game['countries']) == 10
        assert all(c['soldiers'] >= 1 for c in game['countries'].values())
        assert all(c['owner'] is None or c['owner'] in {p['id'] for p in game['players']}
                   for c in game['countries'].values())
        if engine.player_id != 'human':
            engine.npc_step()
            continue
        phase = game['phase']
        if phase == 'reinforce':
            strongest = max(engine.owned(), key=lambda n: game['countries'][n]['soldiers'])
            engine.reinforce({strongest: game['pending_reinforcements']})
        elif phase == 'action':
            source = max(engine.owned(), key=lambda n: game['countries'][n]['soldiers'])
            targets = [(name, c) for name,c in game['countries'].items() if c['owner']!='human']
            target = min(targets, key=lambda item:item[1]['soldiers'])[0]
            if game['countries'][source]['soldiers'] > game['countries'][target]['soldiers']:
                engine.begin_attack(source, target)
            else:
                engine.skip()
        elif phase == 'attacking':
            attack = game['attack']
            if game['countries'][attack['source']]['soldiers'] < game['countries'][attack['target']]['soldiers']:
                engine.stop_attack()
            else:
                engine.roll_phase()
        elif phase == 'conquer_transfer':
            engine.finish_conquest(0)
        else:
            pytest.fail(f'Unknown phase {phase}')
    return game, max_steps


@pytest.mark.parametrize('seed', [1, 4, 17, 28, 99, 2027])
def test_1200_npc_and_human_actions_preserve_rules(seed):
    game, steps = simulate(seed)
    assert steps > 100  # many rounds, battle phases, eliminations and reinforcements
    assert game['round'] > 1
    if game['status'] == 'finished':
        assert len({c['owner'] for c in game['countries'].values()}) == 1
        assert game['winner'] is not None
        assert any(e['kind'] == 'victory' for e in game['events'])
