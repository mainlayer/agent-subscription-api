"""caller.py — Shows how a subscribed agent autonomously calls the Research Agent API.

Usage:
    python client/caller.py \
        --wallet agent-wallet-abc123 \
        --base-url http://localhost:8000

This script models the "caller" side: an agent that already has an active
subscription and wants to invoke the Research Agent's capabilities.

The caller:
  1. Passes its wallet in the X-Payer-Wallet header on every request.
  2. Handles 402 responses gracefully — either retrying after subscribing,
     or surfacing the error to its orchestrator.
  3. Runs several different task types to demonstrate the full capability set.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import httpx


# ---------------------------------------------------------------------------
# Core call helper
# ---------------------------------------------------------------------------


class SubscribedAgentCaller:
    """Reusable caller that injects the subscription wallet on every request."""

    def __init__(self, base_url: str, wallet: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.wallet = wallet
        self._headers = {"X-Payer-Wallet": wallet, "Content-Type": "application/json"}

    async def run_task(
        self,
        task_type: str,
        query: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call POST /agent/run.

        Returns the parsed JSON result on success.
        Raises httpx.HTTPStatusError on non-2xx responses.
        """
        payload = {
            "task_type": task_type,
            "query": query,
            "options": options or {},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/agent/run",
                headers=self._headers,
                json=payload,
            )
            if response.status_code == 402:
                detail = response.json()
                raise SubscriptionRequiredError(
                    wallet=self.wallet,
                    subscribe_url=detail.get("subscribe_url", ""),
                    plans_url=detail.get("plans_url", ""),
                )
            response.raise_for_status()
            return response.json()


class SubscriptionRequiredError(Exception):
    """Raised when the API responds with 402 Payment Required."""

    def __init__(self, wallet: str, subscribe_url: str, plans_url: str) -> None:
        super().__init__(f"Subscription required for wallet={wallet}")
        self.wallet = wallet
        self.subscribe_url = subscribe_url
        self.plans_url = plans_url


# ---------------------------------------------------------------------------
# Demo tasks
# ---------------------------------------------------------------------------


async def demo_web_research(caller: SubscribedAgentCaller) -> None:
    print("\n--- Task: web_research ---")
    result = await caller.run_task(
        task_type="web_research",
        query="What are the latest advances in multi-agent AI systems?",
        options={"max_results": 3},
    )
    print(f"Result:\n{result['result']}")
    print(f"Metadata: {json.dumps(result['metadata'], indent=2)}")


async def demo_summarization(caller: SubscribedAgentCaller) -> None:
    print("\n--- Task: summarization ---")
    long_text = (
        "Multi-agent systems have seen rapid development over the past few years. "
        "Frameworks such as AutoGen, CrewAI, and LangGraph allow developers to "
        "compose networks of specialized agents that collaborate on complex tasks. "
        "Each agent maintains its own context, tools, and objectives while sharing "
        "information through structured message passing. The Mainlayer platform "
        "enables these agents to transact with each other using subscription-based "
        "access control, creating a marketplace of AI capabilities."
    )
    result = await caller.run_task(
        task_type="summarization",
        query=long_text,
        options={"max_sentences": 2},
    )
    print(f"Result:\n{result['result']}")


async def demo_fact_checking(caller: SubscribedAgentCaller) -> None:
    print("\n--- Task: fact_checking ---")
    result = await caller.run_task(
        task_type="fact_checking",
        query="AI agents can autonomously purchase API subscriptions without human involvement.",
    )
    print(f"Result:\n{result['result']}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main(base_url: str, wallet: str) -> None:
    caller = SubscribedAgentCaller(base_url=base_url, wallet=wallet)
    print(f"[caller] Calling Research Agent at {base_url}")
    print(f"[caller] Subscriber wallet: {wallet}")

    try:
        await demo_web_research(caller)
        await demo_summarization(caller)
        await demo_fact_checking(caller)
        print("\n[caller] All tasks completed successfully.")
    except SubscriptionRequiredError as exc:
        print(
            f"\n[caller] 402 Payment Required — wallet={exc.wallet} has no active subscription.\n"
            f"         Subscribe at: {exc.subscribe_url}\n"
            f"         View plans at: {exc.plans_url}",
            file=sys.stderr,
        )
        sys.exit(2)
    except httpx.HTTPStatusError as exc:
        print(
            f"\n[caller] HTTP error {exc.response.status_code}: {exc.response.text}",
            file=sys.stderr,
        )
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call the Research Agent API as a subscribed agent.")
    parser.add_argument(
        "--wallet",
        default="agent-demo-wallet-001",
        help="Wallet identifier for the subscribed agent (passed as X-Payer-Wallet header).",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the agent subscription API.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(base_url=args.base_url, wallet=args.wallet))
