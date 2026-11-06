/* Public view polling and owner-controlled step-by-step NPC simulation.
 * Only server-validated actions modify game state; this file is presentation-only.
 */
(() => {
  'use strict';
  const root = document.getElementById('game-root');
  if (!root) return;
  const status = document.getElementById('simulation-message');
  const stepButton = document.getElementById('step-npc');
  const fastButton = document.getElementById('fast-forward');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  let busy = false;
  let latestVersion = null;

  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const playersById = game => Object.fromEntries(game.players.map(p => [p.id, p]));
  function label(message) { if (status) status.textContent = message; }
  function toggleButtons(disabled) {
    if (stepButton) stepButton.disabled = disabled;
    if (fastButton) fastButton.disabled = disabled;
  }
  function addDie(container, value, variant) {
    const chip = document.createElement('span');
    chip.className = `die ${variant}`;
    chip.textContent = String(value);
    container.appendChild(chip);
  }
  function latestBattle(game) {
    const stage = document.getElementById('dice-stage');
    if (!stage) return;
    const event = [...game.events].reverse().find(e => e.kind === 'dice');
    stage.replaceChildren();
    if (!event) { stage.textContent = 'No dice have been rolled yet.'; return; }
    const heading = document.createElement('p');
    heading.textContent = `${event.source} attacks ${event.target}`;
    stage.append(heading);
    for (const [name, dice, style] of [
      ['Attacker', event.attacker_rolls, 'attack-die'],
      ['Defender', event.defender_rolls, 'defend-die']
    ]) {
      const line = document.createElement('div');
      line.className = 'dice-line';
      line.append(document.createTextNode(`${name}: `));
      dice.forEach(v => addDie(line, v, style));
      stage.append(line);
    }
    const loss = document.createElement('p');
    loss.textContent = `Losses: ${event.source} −${event.attacker_losses} · ${event.target} −${event.defender_losses}`;
    stage.append(loss);
  }
  function events(game) {
    const log = document.getElementById('battle-log');
    if (!log) return;
    const fragment = document.createDocumentFragment();
    [...game.events].reverse().forEach(e => {
      const item = document.createElement('article');
      item.className = `event event-${e.kind}`;
      const meta = document.createElement('span');
      meta.className = 'event-meta';
      meta.textContent = `ROUND ${e.round} · ${e.kind.toUpperCase()}` +
        (e.kind === 'commentary' ? ` · ${e.mode === 'ai' ? 'AI' : 'OFFLINE NARRATION'}` : '');
      const detail = document.createElement('p');
      detail.textContent = e.text;
      item.append(meta, detail);
      fragment.append(item);
    });
    log.replaceChildren(fragment);
  }
  function updateUI(game) {
    const people = playersById(game);
    document.getElementById('round-label').textContent = `Round ${game.round}`;
    document.getElementById('turn-label').textContent = game.turn_name;
    document.getElementById('phase-label').textContent = game.phase.replaceAll('_', ' ');
    document.getElementById('game-status').textContent = game.status.toUpperCase();
    document.querySelectorAll('[data-country-name]').forEach(row => {
      const c = game.countries[row.dataset.countryName];
      if (!c) return;
      row.querySelector('[data-soldiers]').textContent = c.soldiers;
      row.querySelector('[data-controller]').textContent = people[c.owner]?.name || 'Unclaimed';
      row.classList.toggle('own-row', c.owner === 'human');
    });
    document.querySelectorAll('[data-player-id]').forEach(card => {
      const id = card.dataset.playerId;
      const owned = Object.values(game.countries).filter(c => c.owner === id);
      card.querySelector('[data-territories]').textContent = owned.length;
      card.querySelector('[data-armies]').textContent = owned.reduce((a, c) => a + c.soldiers, 0);
      card.querySelector('[data-player-status]').textContent = owned.length ? 'IN GAME' : 'ELIMINATED';
      card.querySelector('[data-player-attacks]').textContent = game.statistics[id]?.attacks || 0;
      card.querySelector('[data-player-conquests]').textContent = game.statistics[id]?.conquests || 0;
    });
    latestBattle(game);
    events(game);
    if (document.getElementById('npc-progress')) {
      document.getElementById('npc-progress').textContent =
        game.status === 'finished' ? 'The game has finished.' : `${game.turn_name} · ${game.phase.replaceAll('_',' ')}`;
    }
    latestVersion = game.version;
  }
  async function readState() {
    const response = await fetch(root.dataset.stateUrl, {credentials: 'same-origin', cache: 'no-store'});
    if (!response.ok) throw new Error('Failed to load the game board.');
    return response.json();
  }
  async function npcStep() {
    const response = await fetch(root.dataset.stepUrl, {
      method: 'POST', credentials: 'same-origin',
      headers: {'X-CSRFToken': csrf, 'Accept': 'application/json'}
    });
    let json;
    try { json = await response.json(); } catch (_) { throw new Error('Server error while simulating the turn.'); }
    if (!response.ok) throw new Error(json.error || 'The simulation could not continue.');
    updateUI(json);
    return json;
  }
  function shouldFinish(game) { return game.status !== 'active' || game.is_human_turn; }
  async function runStep() {
    if (busy) return;
    busy = true; toggleButtons(true);
    try {
      const game = await npcStep();
      label(`${game.turn_name} · ${game.phase.replaceAll('_',' ')}`);
      if (shouldFinish(game)) { await pause(600); location.reload(); }
    } catch (err) { label(err.message); }
    finally { busy = false; toggleButtons(false); }
  }
  async function fastForward() {
    if (busy) return;
    busy = true; toggleButtons(true);
    try {
      let steps = 0;
      let game = await readState();
      while (!shouldFinish(game) && steps < 600) {
        game = await npcStep();
        steps += 1;
        label(`Showing NPC move ${steps} · ${game.turn_name}`);
        await pause(650);  // still display every decision and battle phase
      }
      if (shouldFinish(game)) location.reload();
      else label('Step limit reached. Click fast-forward again to continue.');
    } catch (err) { label(err.message); }
    finally { busy = false; toggleButtons(false); }
  }
  stepButton?.addEventListener('click', runStep);
  fastButton?.addEventListener('click', fastForward);
  document.getElementById('copy-link')?.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      const copy = document.getElementById('copy-link');
      copy.textContent = 'Link copied';
      setTimeout(() => { copy.textContent = 'Copy spectator link'; }, 1800);
    } catch (_) { label('Copy manually from your browser address bar.'); }
  });
  // Shared spectators follow a game without receiving permission to play.
  setInterval(async () => {
    if (busy) return;
    try {
      const game = await readState();
      if (latestVersion === game.version) return;
      updateUI(game);
      if (root.dataset.owner === 'true' && root.dataset.humanTurn === 'false' &&
          (game.is_human_turn || game.status === 'finished')) location.reload();
    } catch (_) { /* Temporary connectivity issues do not erase the board. */ }
  }, 4000);
})();
