"""subscriber.py — Shows how an AI agent autonomously subscribes to the Research Agent API.

Usage:
    python client/subscriber.py \
        --wallet agent-wallet-abc123 \
        --plan pro \
        --base-url http://localhost:8000

This script models the "buyer" side of the agent-to-agent subscription pattern.
The subscribing agent:
  1. Fetches the capabilities endpoint to discover available plans.
  2. Selects the best plan for its needs.
  3. Calls /subscribe to create the subscription.
  4. Optionally follows the checkout_url if payment is still outstanding.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import httpx


async def fetch_capabilities(base_url: str) -> dict:
    """Discover what the agent offers and at what price."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}/agent/capabilities")
        response.raise_for_status()
        return response.json()


async def select_plan(capabilities: dict, preferred_plan: str) -> str:
    """Choose a plan from the capabilities response.

    An autonomous agent would apply business logic here — e.g. pick the
    cheapest plan that satisfies its anticipated call volume.
    """
    available = [p["name"] for p in capabilities.get("plans", [])]
    if preferred_plan in available:
        return preferred_plan
    # Fallback: pick the first available plan
    if available:
        return available[0]
    raise ValueError("No plans available from the agent.")


async def create_subscription(base_url: str, wallet: str, plan: str) -> dict:
    """POST /subscribe to activate a subscription."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/subscribe",
            json={"wallet": wallet, "plan": plan},
        )
        response.raise_for_status()
        return response.json()


async def main(base_url: str, wallet: str, preferred_plan: str) -> None:
    print(f"[subscriber] Discovering capabilities at {base_url} ...")
    capabilities = await fetch_capabilities(base_url)
    print(f"[subscriber] Agent: {capabilities['name']}")
    print(f"[subscriber] Available plans:")
    for plan in capabilities["plans"]:
        calls = plan["calls_per_month"] if plan["calls_per_month"] != -1 else "unlimited"
        print(f"             - {plan['name']}: {calls} calls/month @ ${plan['price_usd']:.2f}/mo")

    chosen_plan = await select_plan(capabilities, preferred_plan)
    print(f"\n[subscriber] Selecting plan: {chosen_plan}")

    print(f"[subscriber] Creating subscription for wallet={wallet} ...")
    subscription = await create_subscription(base_url, wallet, chosen_plan)

    print("\n[subscriber] Subscription result:")
    print(json.dumps(subscription, indent=2))

    if subscription.get("checkout_url"):
        print(
            f"\n[subscriber] Payment required. Direct the agent to complete payment at:\n"
            f"             {subscription['checkout_url']}"
        )
    elif subscription.get("status") == "active":
        print("\n[subscriber] Subscription is ACTIVE. You can now call /agent/run.")
    else:
        print(f"\n[subscriber] Subscription status: {subscription.get('status')}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Subscribe to the Research Agent API.")
    parser.add_argument(
        "--wallet",
        default="agent-demo-wallet-001",
        help="Unique identifier for the subscribing agent.",
    )
    parser.add_argument(
        "--plan",
        default="starter",
        choices=["starter", "pro", "unlimited"],
        help="Subscription plan to purchase.",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the agent subscription API.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(main(base_url=args.base_url, wallet=args.wallet, preferred_plan=args.plan))
    except httpx.HTTPStatusError as exc:
        print(f"[subscriber] HTTP error: {exc.response.status_code} — {exc.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"[subscriber] Error: {exc}", file=sys.stderr)
        sys.exit(1)
