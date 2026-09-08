# Google Docs Operator Chat — setup

Doc: https://docs.google.com/document/d/1fEuErs8mTMzSoJm4WMesxmhsfqvnlhzzFINycbRCIeU/edit

## Talk to the AI

**Terminal (recommended, free):**
```bash
./run_all.sh talk
```
Type normally. `/quit` to leave. Same tags as below.

In the Google Doc (or local fallback `data/intel/operator_chat.md`):

```
USER: paper is weak — what is actually wrong? [[status]] [[math]]
```

Commands (optional tags anywhere in your message):

| Tag | Effect |
|-----|--------|
| `[[status]]` | Honest stack/math status (says DOWN if down) |
| `[[math]]` | Formula catalog summary |
| `[[explain last loss]]` | Honest postmortem + weight fixes if warranted |
| `[[evolve]]` | Guarded free-agent / code evolve |
| `[[fix]]` | Assess + allowlisted edits |
| `[[train]]` | Keep training alive (does not tear down trains) |
| `[[mood]]` | Current concern/confidence |
| `[[help]]` | Protocol reminder |

The AI replies as `AI: …` with thoughts/opinions, then specifics. Persona: **honest and direct** — no sugarcoating, no fake optimism.

## Start

```bash
./run_all.sh doc-chat          # daemon (also: operator-doc)
./run_all.sh doc-chat-once     # one poll
```

Idle watchdog restarts it if it dies.

## Google auth (for live Doc)

1. Enable Google Docs API on a GCP project.
2. Create a **service account**, download JSON key → `data/secrets/google_service_account.json`
3. Or set `GOOGLE_SERVICE_ACCOUNT_JSON=/absolute/path/to/key.json` in `.env`
4. **Share the Doc** with the service account email as Editor.
5. `./venv/bin/pip install google-api-python-client google-auth`
6. Restart: `./run_all.sh doc-chat`

Until auth works, the same protocol runs on `data/intel/operator_chat.md`.

## Code-edit autonomy

When something is actually bad, the operator:

1. States the defect specifically
2. Adjusts `data/intel/operator_math_overrides.json` (rank multipliers)
3. Enqueues `data/agi/inbox/OPERATOR_DOC_PROMPT.md` for free-agent
4. May call `evolve_once` / `free_agent_step` on allowlisted hooks/overlay

Never: delete `models/`, shrink universe, skip train phases, force-push.
