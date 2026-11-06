# Project changes against the UCT INF4001N marking sheet (56 marks)

This document maps implementation features, not awarded marks. Each rubric item is scored 0–4 by the assessors.

| Rubric criterion | Implementation evidence | Status |
|---|---|---|
| Database layer | `game/repository.py` isolates MongoDB, `MONGO_URI` from environment | Implemented |
| Connection to database | MongoDB Atlas URI + `/health` ping | Implemented; real connection must be tested |
| Database design | Separate users/games/login-attempts collections, unique/compound/TTL indexes, game schema and optimistic versioning | Implemented |
| Coding structure | Flask controller, game/domain engine, repository, catalogue, AI integration and independent tests | Implemented |
| Object-oriented concepts | `GameEngine`, `GameRepository`, `BattleCommentator`, `User` | Implemented |
| Data validation, controls and security | Server-side rule validation, CSRF, cookie controls, rate-limited login, version conflict detection | Implemented |
| Functionality | All specified actions and turn states, victory/elimination | Implemented; browser validation still needed |
| Works correctly, lists/searching/filtering/viewing | Public active games, owner's game list, nation selection, state updates | Implemented; browser validation still needed |
| User interface | Responsive territory tables, dice phases, player cards, analytics, event history | Implemented; browser validation still needed |
| Ease of navigation | Home, login/register, create, game view, separate forms for each phase | Implemented |
| Authentication/authorization | Flask-Login, owner-only actions, public spectator GETs | Implemented; browser validation still needed |
| Sophistication/complexity | Pure game state machine, NPC heuristic plans, one-step fast-forward, event histories | Implemented |
| AI application | OpenAI-compatible chat-completions request on each dice phase; explicit offline fallback | Implemented but requires valid API configuration to demonstrate |
| Overall evidence of effort | Unit tests, simulations, documented population sources and detailed README | Implemented |

Outstanding real-world work: **live MongoDB Atlas integration**, **AI provider verification**, **deployment to a public HTTPS host**, **submission/demo credentials**, and manual browser checks with multiple sessions. These cannot be completed with placeholder credentials alone.
