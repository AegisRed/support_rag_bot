# Support RAG Assistant Bot

Production-style Telegram bot for first-line support triage with retrieval-augmented generation (RAG), strict answer boundaries, and controlled escalation to a human operator.

The project demonstrates a pragmatic support workflow:
- accept an incoming support ticket as a plain Telegram message;
- retrieve relevant knowledge base articles from a local vectorized store;
- answer only when the available context is sufficient;
- ask a short follow-up only when one more user message can realistically unlock a grounded answer;
- stop guessing and hand off the ticket when the case is account-specific, operational, or requires manual investigation.

This repository is intentionally focused on **decision quality and boundaries**, not on a specific real-world knowledge base.

## Why this project exists

Most support queues contain repetitive questions that are already covered by internal docs or a public help center. The hard part is not generating text — it is deciding **when the assistant is allowed to answer** and **when it should stay quiet and escalate**.

This bot is built around that principle.

## Core capabilities

- Telegram bot built on `aiogram` 3.x
- RAG pipeline backed by Gemini embeddings
- Local SQLite storage for:
  - knowledge base documents;
  - precomputed embeddings;
  - ticket decision logs;
- conversational support flow without noisy inline controls during active ticket handling
- dynamic clarification strategy instead of fixed questionnaires
- configurable decision thresholds through environment variables
- optional exposure of internal decision diagnostics for debugging/demo mode
- seed knowledge base for demo and evaluation scenarios

## What the bot does

1. Receives a support issue from a user.
2. Embeds the incoming message and searches the local knowledge base.
3. Sends retrieved context plus ticket history to Gemini.
4. Gemini returns exactly one decision:
   - `answer`
   - `clarify`
   - `handoff`
5. The application applies an additional server-side gate before presenting the final result.
6. The full decision is logged to SQLite for audit and later analysis.

## Decision policy

The assistant is designed to prefer a safe fallback over a confident hallucination.

### `answer`
Used only when the retrieved knowledge base clearly supports a concrete reply.

Typical examples:
- password reset instructions;
- invoice download path;
- known feature availability by plan;
- documented rate-limit behavior.

### `clarify`
Used only when a short follow-up can realistically turn the case into a grounded answer.

Typical examples:
- the user mentions login issues but not whether this is password reset, 2FA recovery, or a temporary service issue;
- the request is missing one critical detail that maps directly to a documented KB branch.

### `handoff`
Used when the bot should stop guessing.

Typical examples:
- 5xx/server-side errors;
- account-specific problems;
- cases that require logs, admin access, billing actions, or private system checks;
- ambiguous issues that would remain ambiguous even after another follow-up.

## Current handoff model

This version implements **handoff state**, not a full operator routing backend.

That means:
- the bot can stop auto-answering and mark the ticket as requiring a human;
- the user remains in a dedicated ticket state until `/exitticket`;
- the project does **not yet** forward the ticket to a live operator chat, forum topic, CRM, or helpdesk system.

This is intentional and should be stated clearly in production discussions.

## Architecture

```text
Telegram User
    ↓
aiogram Router / FSM
    ↓
Ticket Orchestrator
    ├─ embed query via Gemini
    ├─ retrieve top-K KB hits from SQLite
    ├─ ask Gemini for structured decision
    ├─ apply local safety gate
    └─ log result to SQLite
```

### Main components

#### `support_rag_bot/bot.py`
Application entrypoint. Initializes:
- bot instance;
- dispatcher and FSM storage;
- Gemini service;
- RAG service;
- knowledge base bootstrap;
- Telegram bot commands and descriptions.

#### `support_rag_bot/routers/start.py`
Start/help/menu handlers.

#### `support_rag_bot/routers/tickets.py`
Ticket lifecycle orchestration:
- start ticket;
- accept free-form text;
- clarification loop;
- handoff mode;
- exit flow.

#### `support_rag_bot/services/gemini_service.py`
Wrapper around Gemini API for:
- document embeddings;
- query embeddings;
- structured decision generation.

#### `support_rag_bot/services/rag_service.py`
Main business logic:
- bootstrap KB;
- retrieval;
- grounding checks;
- answer formatting;
- link display control;
- final decision shaping.

#### `support_rag_bot/services/storage.py`
SQLite persistence layer.

#### `support_rag_bot/services/seed.py`
Demo knowledge base used for local evaluation.

## Repository structure

```text
.
├── run.py
├── Dockerfile
├── requirements.txt
├── .env.example
└── support_rag_bot/
    ├── bot.py
    ├── config.py
    ├── keyboards.py
    ├── logging_setup.py
    ├── models.py
    ├── states.py
    ├── routers/
    │   ├── start.py
    │   └── tickets.py
    └── services/
        ├── gemini_service.py
        ├── rag_service.py
        ├── seed.py
        └── storage.py
```

## Tech stack

- Python 3.11+
- aiogram 3.x
- Google Gemini API
- SQLite + aiosqlite
- Pydantic / pydantic-settings

## Configuration

Create `.env` from `.env.example`.

### Required variables

```env
TELEGRAM_BOT_TOKEN=...
GEMINI_API_KEY=...
```

### Full example

```env
TELEGRAM_BOT_TOKEN=123456:replace_me
GEMINI_API_KEY=replace_me
GEMINI_GENERATION_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
KB_SOURCE_SITES=https://help.northstar.test,https://billing.northstar.test,https://status.northstar.test
DB_PATH=data/support_rag.sqlite3
TOP_K=4
MIN_SIMILARITY_SCORE=0.72
MIN_SELF_CONFIDENCE=0.78
MAX_CLARIFICATION_ROUNDS=2
SHOW_DECISION_DETAILS=false
LOG_LEVEL=INFO
ADMIN_USER_IDS=
```

### Important settings

#### `MIN_SIMILARITY_SCORE`
Minimum retrieval quality required before the bot is comfortable grounding an answer.

Higher value:
- fewer auto-replies;
- more handoffs;
- lower hallucination risk.

Lower value:
- more aggressive auto-replies;
- higher risk of answering from weak matches.

#### `MIN_SELF_CONFIDENCE`
Minimum model confidence required for a final grounded response.

#### `MAX_CLARIFICATION_ROUNDS`
Upper bound for clarification loops.

Recommended production behavior: keep this low. The support assistant should not interrogate the user indefinitely.

#### `SHOW_DECISION_DETAILS`
When enabled, the bot can expose debugging-style output useful in demos or internal QA. Recommended value for user-facing environments: `false`.

#### `ADMIN_USER_IDS`
Comma-separated Telegram user IDs allowed to run administrative commands such as reindexing.

## Local setup

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

## Docker

Build and run locally:

```bash
docker build -t support-rag-bot .
docker run --rm -it --env-file .env support-rag-bot
```

## Telegram commands

- `/start` — open start screen
- `/newticket` — begin a new ticket explicitly
- `/exitticket` — end current ticket and return to menu
- `/kb` — list seeded knowledge base documents
- `/examples` — show example support prompts
- `/reindex` — rebuild seeded embeddings (admin-only if `ADMIN_USER_IDS` is configured)

## Example interaction

### Answer path

User:
> Я не вижу кнопку экспорта CSV на тарифе Starter

Bot:
> На тарифе Starter экспорт CSV недоступен. Эта функция есть на Growth и Enterprise. Если нужен экспорт, проверь тариф workspace или передай запрос на апгрейд.

### Clarification path

User:
> Не получается войти в аккаунт

Bot:
> Понял. Это проблема со входом в существующий аккаунт или вы пытаетесь восстановить доступ?

### Handoff path

User:
> При авторизации сайт возвращает ошибку 500

Bot:
> Если при входе уже возникает ошибка 500, это похоже на серверную или внутреннюю проблему. Тут лучше не гадать по базе знаний — такой кейс стоит передать оператору. Завершить тикет можно командой /exitticket.

## Seed knowledge base

The repository ships with a small demo KB covering common SaaS support topics such as:
- password reset;
- lost 2FA access;
- invoices and billing;
- subscription cancellation policy;
- CSV export availability;
- API rate limits and 429 handling;
- webhook retry policy;
- SSO requirements;
- service status/incidents.

This KB is synthetic and exists to demonstrate retrieval and decision logic.

## Logging and auditability

Every processed ticket is written to SQLite with:
- timestamp;
- Telegram user ID;
- username;
- original input text;
- final mode;
- confidence value;
- generated reply;
- short reasoning string;
- selected source metadata;
- missing-information hints.

This makes the project easier to review, debug, and evaluate offline.

## Operational limitations

The current repository is intentionally lightweight. Before shipping to a real support environment, you would usually add:
- real KB ingestion from Markdown, HTML, PDF, Confluence, Notion, or a help center API;
- chunking and metadata-aware indexing;
- live operator routing;
- admin dashboard or ticket monitor;
- rate limiting and retry policy for upstream model calls;
- structured observability and metrics;
- secrets management beyond local `.env`;
- tests and CI.

## Recommended production next steps

1. Replace seed documents with a real ingestion pipeline.
2. Add operator handoff integration:
   - Telegram admin chat;
   - forum topics;
   - CRM/helpdesk bridge.
3. Add regression tests for decision outcomes.
4. Introduce caching and backoff around Gemini API calls.
5. Add message deduplication and abuse/rate controls.
6. Split storage into:
   - relational logs;
   - vector index optimized for retrieval at scale.

## Security notes

- Do not commit `.env` to the repository.
- Treat `GEMINI_API_KEY` and `TELEGRAM_BOT_TOKEN` as secrets.
- The demo seed KB contains no real customer data.
- SQLite is sufficient for a local demo but not ideal for high-concurrency production support workloads.

## Troubleshooting

### Bot starts but does not answer
Check:
- `TELEGRAM_BOT_TOKEN` is valid;
- webhook is not conflicting with polling mode;
- Gemini key is present;
- dependencies are installed correctly.

### Bot answers too aggressively
Increase:
- `MIN_SIMILARITY_SCORE`
- `MIN_SELF_CONFIDENCE`

Reduce:
- `MAX_CLARIFICATION_ROUNDS`

### Bot escalates too often
Lower thresholds gradually and test against a labeled set of representative tickets.

### Reindex is needed after KB changes
Run:

```bash
/reindex
```

Or rebuild the database by removing the local SQLite file and starting the bot again.

## License / usage

This repository is suitable as a demo project, technical assignment deliverable, or base template for a safer support assistant.

If you want, the next practical upgrade is straightforward: connect real operator routing and replace the synthetic KB with a true ingestion pipeline.


## AmoCRM AI Copilot test demo

This branch also contains a small web prototype for the O-complex test assignment. It reuses the same grounded retrieval pipeline, but presents the result in the workflow expected from an AmoCRM manager assistant:

1. accept the latest client message;
2. optionally accept context from the CRM card (current plan, deal note, manager note);
3. retrieve relevant entries from the short knowledge base;
4. return two separated outputs:
   - a polite reply that is safe to send to the client;
   - a private manager hint with an upsell only when the client's need clearly matches a documented higher-plan capability.

The prototype intentionally does **not** pretend to be a live AmoCRM OAuth integration. The HTTP endpoint is the integration boundary; a production adapter can pass messages and deal context from AmoCRM into the same service.

### Run the demo

For the web demo only, `TELEGRAM_BOT_TOKEN` is not required.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env        # Windows: Copy-Item .env.example .env
# Put GEMINI_API_KEY into .env
python run_demo.py
```

Open `http://127.0.0.1:8080`.

The page includes three ready-made scenarios useful for a 1–2 minute recording:
- Starter customer needs CSV export → grounded Growth upsell;
- customer needs SAML SSO → grounded Enterprise upsell;
- password-reset problem → support answer without forcing an upsell.

### HTTP contract

`POST /api/assist`

```json
{
  "client_message": "У нас Starter, но нужен экспорт CSV. Где его включить?",
  "manager_context": "Текущий тариф: Starter."
}
```

Response:

```json
{
  "client_reply": "Клиентский ответ...",
  "manager_hint": "Внутренняя подсказка менеджеру...",
  "upsell_product": "Growth",
  "confidence": 0.93,
  "sources": []
}
```

The source list is populated with the KB documents actually cited by the model. If retrieval or model confidence is too weak, the service falls back to a safe clarification and explicitly tells the manager not to upsell blindly.

### Suggested 1–2 minute demo script

Show the CSV scenario first: enter a Starter client message, run the assistant, and point out that the response is split into client-facing and private manager blocks. Then switch to the password-reset sample to demonstrate that the system does not invent an upsell when there is no relevant commercial opportunity. Finish by briefly mentioning Python/FastAPI, Gemini structured generation + embeddings, SQLite RAG storage, and the safety gate that validates similarity, confidence and citations.
