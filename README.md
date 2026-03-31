# Agent Subscription API

An AI agent subscription API pattern — AI agents can subscribe to and call other AI agents autonomously, with billing managed by [Mainlayer](https://mainlayer.xyz).

## What This Demonstrates

This template shows the **agent-to-agent subscription pattern**:

1. A **Research Agent** exposes capabilities (web research, summarization, fact-checking) behind a subscription gate.
2. **Subscriber agents** discover the agent's capabilities, choose a plan, and subscribe — all programmatically.
3. **Caller agents** pass their wallet identifier on each API call. Mainlayer verifies the subscription and tracks usage.
4. The agent owner earns recurring revenue without building any billing infrastructure.

```
Subscriber Agent                Research Agent API           Mainlayer
      │                               │                          │
      │  GET /agent/capabilities      │                          │
      │─────────────────────────────▶│                          │
      │  {plans, capabilities}        │                          │
      │◀─────────────────────────────│                          │
      │                               │                          │
      │  POST /subscribe              │                          │
      │  {wallet, plan}               │                          │
      │─────────────────────────────▶│  POST /subscriptions     │
      │                               │─────────────────────────▶│
      │                               │  {subscription_id, ...}  │
      │                               │◀─────────────────────────│
      │  {subscription_id, status}    │                          │
      │◀─────────────────────────────│                          │
      │                               │                          │
      │  POST /agent/run              │                          │
      │  X-Payer-Wallet: wallet-123   │                          │
      │─────────────────────────────▶│  GET /entitlements/check │
      │                               │─────────────────────────▶│
      │                               │  {active: true, ...}     │
      │                               │◀─────────────────────────│
      │                               │  POST /usage             │
      │                               │─────────────────────────▶│
      │  {result}                     │                          │
      │◀─────────────────────────────│                          │
```

## Quick Start

### 1. Clone and configure

```bash
cp .env.example .env
# Edit .env — add your MAINLAYER_API_KEY and RESOURCE_ID
```

### 2. Run with Docker Compose

```bash
docker compose up
```

### 3. Or run locally

```bash
pip install -r requirements.txt
uvicorn src.main:app --reload
```

The API is now available at `http://localhost:8000`.

## API Reference

### Public endpoints (no auth required)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `GET` | `/agent/capabilities` | Plans, pricing, and capabilities |

### Subscription endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/subscribe` | Create a subscription |
| `GET` | `/subscriptions/{wallet}` | Retrieve subscription status |

### Agent endpoints (subscription required)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/agent/run` | Execute an agent task |

Pass the subscriber wallet in the `X-Payer-Wallet` header:

```bash
curl -X POST http://localhost:8000/agent/run \
  -H "X-Payer-Wallet: your-wallet-id" \
  -H "Content-Type: application/json" \
  -d '{"task_type": "web_research", "query": "latest AI agent frameworks"}'
```

### Subscription plans

| Plan | Calls/month | Price |
|------|-------------|-------|
| `starter` | 100 | $5.00/mo |
| `pro` | 1,000 | $20.00/mo |
| `unlimited` | Unlimited | $50.00/mo |

### Task types

| Type | Description |
|------|-------------|
| `web_research` | Search the web and return ranked results |
| `summarization` | Summarize text or a topic |
| `fact_checking` | Assess the factual accuracy of a claim |

## Client Examples

### Subscribing (agent buyer)

```bash
python client/subscriber.py --wallet my-agent-wallet --plan pro
```

Or in Python:

```python
import asyncio, httpx

async def subscribe():
    async with httpx.AsyncClient() as client:
        # 1. Discover capabilities
        caps = (await client.get("http://localhost:8000/agent/capabilities")).json()
        print(caps["plans"])

        # 2. Subscribe
        sub = (await client.post(
            "http://localhost:8000/subscribe",
            json={"wallet": "my-agent-wallet", "plan": "pro"},
        )).json()
        print(sub["status"])

asyncio.run(subscribe())
```

### Calling (subscribed agent)

```bash
python client/caller.py --wallet my-agent-wallet
```

Or in Python:

```python
import asyncio, httpx

async def call_agent():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/agent/run",
            headers={"X-Payer-Wallet": "my-agent-wallet"},
            json={
                "task_type": "summarization",
                "query": "Explain how agent-to-agent billing works.",
                "options": {"max_sentences": 3},
            },
        )
        if response.status_code == 402:
            # No active subscription — redirect to subscribe
            detail = response.json()["detail"]
            print(f"Subscribe at: {detail['subscribe_url']}")
        else:
            print(response.json()["result"])

asyncio.run(call_agent())
```

### 402 Payment Required

When a caller has no active subscription the API returns:

```json
{
  "detail": {
    "error": "subscription_required",
    "message": "An active subscription is required to use this agent.",
    "subscribe_url": "https://your-agent.example.com/subscribe",
    "resource_id": "res_abc123",
    "plans_url": "https://your-agent.example.com/agent/capabilities"
  }
}
```

An autonomous agent handles this by calling `subscribe_url` with its wallet and chosen plan, then retrying the original request.

## Project Structure

```
agent-subscription-api/
├── src/
│   ├── main.py          # FastAPI app — routes and middleware
│   ├── mainlayer.py     # Mainlayer API client (entitlements, subscriptions, usage)
│   ├── agent_logic.py   # Agent capabilities (web_research, summarization, fact_checking)
│   └── models.py        # Pydantic request/response models
├── client/
│   ├── subscriber.py    # Example: agent subscribes to this API
│   └── caller.py        # Example: subscribed agent calls this API
├── tests/
│   └── test_api.py      # 25+ tests with mocked Mainlayer client
├── .github/
│   └── workflows/
│       └── ci.yml       # CI: test, lint, Docker build
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Running Tests

```bash
pytest tests/ -v --asyncio-mode=auto
```

With coverage:

```bash
pytest tests/ -v --cov=src --cov-report=term-missing --asyncio-mode=auto
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MAINLAYER_API_KEY` | Yes | API key from the Mainlayer dashboard |
| `RESOURCE_ID` | Yes | Mainlayer resource ID for this agent |
| `PUBLIC_BASE_URL` | No | Public URL (used in 402 response bodies) |
| `HOST` | No | Bind host (default: `0.0.0.0`) |
| `PORT` | No | Bind port (default: `8000`) |
| `LOG_LEVEL` | No | Uvicorn log level (default: `info`) |

## Extending This Template

- **Replace mock capabilities**: Edit `src/agent_logic.py` to wire up real search APIs, LLMs, or data pipelines.
- **Add new task types**: Add a value to `TaskType` in `models.py`, implement a handler in `agent_logic.py`, and register it in `_HANDLERS`.
- **Adjust plans**: Update `get_capabilities()` in `main.py` and the corresponding plan records in Mainlayer.
- **Add authentication**: Layer an API key or OAuth middleware on top of the Mainlayer subscription check for additional security.

## Mainlayer Integration

This template uses [Mainlayer](https://mainlayer.xyz) for:

- **Entitlement checks** — verify a wallet has an active subscription before serving a request.
- **Subscription creation** — create and manage subscriptions on behalf of subscriber agents.
- **Usage tracking** — record each API call against the subscription's monthly quota.

All Mainlayer communication is encapsulated in `src/mainlayer.py`. To point at a different environment set `MAINLAYER_API_KEY` and `RESOURCE_ID` accordingly.
