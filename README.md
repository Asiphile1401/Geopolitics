# INF4001N — Geopolitics Game (improved Flask application)

A single-player, ten-country strategy game based on the **University of Cape Town INF4001N 2027 Honours Entrance Exam** brief. A human plays against three rule-based, strategic NPCs. Gameplay is public to spectators; only the authenticated owner can make moves. Multiple games can be saved and resumed independently.

## 1. Features implemented

- **195-country selection** from a local, documented 2026 Worldometer population snapshot. At the start of each game, the user chooses one country and nine other countries are randomly drawn. Three NPCs each receive an initial country; the remaining six are unclaimed.
- **Population soldier bands** from the exam (1–9 soldiers) with unit tests at every boundary.
- **Random first player** and correctly tracked turns/rounds. At the start of rounds 2+, a player receives exactly two soldiers per controlled country; humans allocate their own reinforcements among controlled countries.
- **One attack per turn**, resolved in interactive dice phases. The number of paired attacker/defender dice is `min(attacking soldiers - 1, defending soldiers)`. Dice are rolled independently in the range 1–6; strictly higher roll wins; ties kill no soldier. If the attacker drops to one soldier, the turn ends. Players can also stop the attack manually.
- **Conquest and soldier transfer.** Winning a territory grants `max(2, starting country soldier value // 2)` soldiers to that territory; the player may transfer more from the attacking army, leaving at least one soldier behind. Transfers between already controlled territories can occur before starting an attack.
- **Strategic NPCs** that reinforce, consolidate armies, evaluate targets, attack only if reasonably viable, decide whether to continue, and explain their reasoning in the event log. NPCs no longer receive double reinforcements from fast-forward.
- **Step-by-step NPC simulation** and a fast-forward animation that displays each decision and dice phase. The public game page also refreshes automatically for spectators.
- **AI battle commentary integration** through a configurable OpenAI-compatible chat-completions endpoint. With placeholders or an API outage, clearly labelled offline narration is used instead. Placeholder narration must **not** be presented as LLM output.
- **Basic game analytics** (army/territory counts, attacks and conquests for each player), full battle log, and clickable public spectator links.
- **Authentication, CSRF protection, input validation, session protection, login attempt throttling**, owner-only state-changing actions, and version-checked MongoDB updates to reduce double-submit and multi-tab conflicts.

## 2. Project structure

```text
app.py                       Flask controller routes and app factory
Procfile                     gunicorn entry point
requirements.txt             Python dependencies
.env.example                 placeholders (safe to commit)
data/countries.json          195-country 2026 population snapshot
game/engine.py               turn states, battles, reinforcements, NPCs
 game/catalog.py              population snapshot loader
 game/commentary.py           configurable AI and offline narration
 game/repository.py           isolated MongoDB persistence and migrations
scripts/update_populations.py optional country-data refresh
static/style.css             responsive board styling
static/game.js               spectator updates and visible NPC fast-forward
templates/                   HTML pages with CSRF form protection
tests/                       standalone game-rule and simulation checks
```

## 3. Run locally (MongoDB Atlas; no local MongoDB installation needed)

**Requirements:** Python 3.11+ (3.12 or 3.13 recommended), internet access to MongoDB Atlas, and credentials for your own MongoDB Atlas cluster.

1. Unzip the project and open the project folder in VS Code or another terminal.
2. Create and activate a virtual environment:

   **Windows PowerShell:**
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   **macOS/Linux:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` (Windows: `Copy-Item .env.example .env`; macOS/Linux: `cp .env.example .env`). Set:

   | Variable | Example placeholder / value | Purpose |
   |---|---|---|
   | `SECRET_KEY` | `YOUR_LONG_RANDOM_SECRET_KEY_HERE` | Flask session and CSRF signing secret; replace with a strong random value |
   | `MONGO_URI` | `mongodb+srv://YOUR_DB_USERNAME:YOUR_DB_PASSWORD@YOUR_CLUSTER.mongodb.net/geopolitics_game?retryWrites=true&w=majority` | MongoDB Atlas connection including the database name |
   | `AI_API_URL` | `https://YOUR_AI_PROVIDER.example/v1/chat/completions` | OpenAI-compatible endpoint; optional until AI is enabled |
   | `AI_API_KEY` | `YOUR_AI_API_KEY` | AI provider key; never hard-code or commit |
   | `AI_MODEL` | `YOUR_CHAT_MODEL` | Exact model supported by the provider |
   | `COOKIE_SECURE` | `false` locally, `true` when deployed over HTTPS | Controls secure session cookies |
   | `FLASK_DEBUG` | `false` | Debugger switch; **never** enable publicly |

   Note: `AI_API_URL`, `AI_API_KEY` and `AI_MODEL` can remain placeholders while you test. The application will use transparent offline commentary. **`MONGO_URI` must contain real MongoDB Atlas credentials to run.** Do not leave `SECRET_KEY` as a placeholder in deployment.

5. In MongoDB Atlas, create a database user with only the necessary permissions (readWrite on `geopolitics_game`) and configure **Network Access** to allow the IP address of your computer or deployment server. URL-encode punctuation in database passwords used in the URI. DNS must be able to resolve the Atlas SRV hostname.
6. Start the application:
   ```bash
   python app.py
   ```
7. Open `http://127.0.0.1:5000`. Visit `http://127.0.0.1:5000/health` to confirm the database connection. Register a test account, sign in, create a game and test both human and NPC actions.

For production, run Gunicorn from `Procfile`: `gunicorn app:app --bind 0.0.0.0:${PORT:-8000}`. For local Windows usage, prefer `python app.py` (Gunicorn is generally for Linux hosts).

### Important setup/security notes

- `.env` is excluded by `.gitignore`, and **no real credentials are included** in this ZIP.
- Passwords are stored as Werkzeug hashes, not plaintext. For the exam, create a dedicated app account for assessors and grant the required database access separately.
- Only **POST** forms change game state or log the user out; CSRF tokens are verified. Public users can only view `/game/<id>` and `/game/<id>/state`.
- Do not use personal database admin credentials for the assessment. Instead, create a restricted test user as instructed by the exam and provide the credentials or access through the official submission channel.
- The app performs a **best-effort upgrade of old starter user/game records** during first database initialization. Their historical turn positions cannot be reconstructed perfectly. Start new games after upgrading for the strict game rules.

## 4. How to play

1. Register/login, select your starting country and create a game.
2. The human or one of the NPCs is randomly assigned the first turn. If an NPC starts, use **Play next NPC decision** or **Fast-forward until your turn**. Fast-forward updates the visible log and dice display at each step.
3. In rounds 2+, allocate the full reinforcement allowance to one or more countries.
4. On your turn, optionally transfer soldiers between your territories, then **attack once** or **skip**.
5. When attacking, choose a source and target; press **Roll next combat phase** to show paired dice outcomes. Continue or stop. An attack also ends automatically if the source reaches one soldier.
6. After conquering a territory, accept the awarded soldiers and optionally transfer more soldiers to the new territory. Your turn then ends.
7. Conquer **all ten** territories to win. If you lose your last territory, you are eliminated but can still spectate your game's NPCs.

## 5. Refresh population data

The bundled snapshot covers **all 195 countries listed on Worldometer's country reference page for 2026** and works offline. To refresh before submission:

```bash
python scripts/update_populations.py
```

This script fetches `https://www.worldometers.info/geography/how-many-countries-are-there-in-the-world/`, checks that exactly 195 country rows are present, and atomically replaces `data/countries.json`. New games use the updated data; existing games keep the population and starting-soldier values captured at their creation.

## 6. Test

After installing dependencies, also install `pytest`:

```bash
python -m pip install pytest
python -m pytest -q
```

The included tests cover the soldier bands, round timing, attack dice count and pairwise results, ties, soldier loss, conquest bonuses, transfers, elimination, victory conditions, strategic NPC moves, catalogue coverage, AI fallback, and longer simulated games. **Before submission also perform browser/Atlas end-to-end testing** with a real connected database and an actual AI provider key. Unit tests do not verify a live deployment.

Suggested manual smoke test:

- Register/login/logout; try duplicate username and invalid/forged CSRF token.
- Start two games; switch between them and confirm states remain separate.
- Confirm public link works in a logged-out private browser tab; try POSTing as spectator/another account (must be rejected).
- Test a roll where the dice tie, a failed attack when down to one soldier, a successful conquest, and the occupancy transfer.
- Reach round 2 and confirm reinforcements exactly once per eligible player.
- Watch an NPC take an action, then fast-forward. Verify no dice event is skipped from the visual log.
- Configure valid `AI_API_*` values and ensure actual LLM commentary appears; remove the values and ensure only *offline narration* appears.
- Run the production `/health` check on the deployed URL.

## 7. Deploy / exam submission checklist

Deploy to any Python-capable HTTPS host that supports a long-running Flask/Gunicorn process (e.g. a container host). Set `SECRET_KEY`, `MONGO_URI`, `COOKIE_SECURE=true`, and optional `AI_API_*` environment variables in the host dashboard. Ensure MongoDB Atlas network access permits the hosting environment. Set `FLASK_ENV=production` to reject the development secret.

Submit to the **INF4001 Amathuba** assignment folder:

- [ ] Source ZIP (this project, without `.env` or `.venv`)
- [ ] Real URL to the **deployed** application
- [ ] Dedicated application username and password for assessors
- [ ] Assessors' database access, as specified in the examination instructions
- [ ] README with installation and execution guidance
- [ ] Verify tests, actual AI narration, login/access control and gameplay in your deployed environment

**Limits of this packaged deliverable:** no real deployment, live Atlas connection, app account for assessors, or third-party API credential is provided. They must be configured and verified by the owner of the application. The AI integration is implemented but performs real LLM calls only after valid settings are supplied. The browser integration has not been validated here against a live deployment.
#   G e o p o l i t i c s  
 #   G e o p o l i t i c s  
 