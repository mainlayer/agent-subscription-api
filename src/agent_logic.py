"""Agent capability implementations.

These are the actual agent capabilities exposed through the subscription API.
In production replace the mock implementations below with real calls to:
- Search APIs (Bing, Google, Tavily, Perplexity)
- LLM APIs (Claude, GPT-4, Ollama)
- Data services (knowledge bases, databases)
- Custom ML models or microservices

The public interface `execute_agent_task()` is deliberately kept clean so the
underlying implementation can be swapped freely without changing the API contract.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Any

try:
    from models import AgentTask, AgentTaskResult, TaskType
except ImportError:
    from src.models import AgentTask, AgentTaskResult, TaskType  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _deterministic_hash(text: str) -> str:
    """Return a short deterministic hash used to seed mock outputs."""
    return hashlib.sha256(text.encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Web research
# ---------------------------------------------------------------------------


async def _web_research(query: str, options: dict[str, Any]) -> str:
    """Simulate async web research.

    PRODUCTION INTEGRATION:
    - Call search APIs: Tavily (recommended for agents), SerpAPI, Bing Search API
    - Filter results by relevance and recency
    - Aggregate snippets with proper attribution
    - Handle rate limits and API errors gracefully

    Example (using Tavily):
        import tavily
        client = tavily.AsyncTavilyClient(api_key=...)
        context = await client.get_search_context(query)
        return context
    """
    # Simulate network latency
    await asyncio.sleep(0.05)

    max_results: int = int(options.get("max_results", 3))
    seed = _deterministic_hash(query)

    sources = [
        f"https://example.com/article-{seed}-{i}" for i in range(1, max_results + 1)
    ]

    snippets = [
        f"[Result {i}] Relevant information about '{query}': "
        f"According to source {i}, the key findings are consistent with "
        f"recent literature and suggest a multi-faceted approach to the topic."
        for i in range(1, max_results + 1)
    ]

    formatted = "\n\n".join(
        f"Source {i}: {url}\n{snippet}"
        for i, (url, snippet) in enumerate(zip(sources, snippets), 1)
    )

    return (
        f"Web research results for: '{query}'\n"
        f"({'  '.join(sources)})\n\n"
        f"{formatted}"
    )


# ---------------------------------------------------------------------------
# Summarization
# ---------------------------------------------------------------------------


async def _summarize(query: str, options: dict[str, Any]) -> str:
    """Summarize the provided text or topic.

    PRODUCTION INTEGRATION:
    - Use Claude API for high-quality summaries
    - Support configurable options: max_sentences, style, focus area
    - Cache long-lived summaries for repeated queries
    - Handle large documents with chunking

    Example (using Claude):
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=...)
        max_sentences = int(options.get("max_sentences", 3))
        message = await client.messages.create(
            model="claude-opus-4-1",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": f"Summarize in {max_sentences} sentences:\\n{query}"
            }]
        )
        return message.content[0].text
    """
    await asyncio.sleep(0.03)

    max_sentences: int = int(options.get("max_sentences", 3))
    words = re.findall(r"\w+", query)
    word_count = len(words)

    # Produce a mock summary that references the input
    key_terms = ", ".join(dict.fromkeys(w.lower() for w in words[:5] if len(w) > 3))

    sentences = [
        f"The provided content discusses {key_terms} across {word_count} words.",
        f"The main themes identified are related to {key_terms}.",
        "Further analysis suggests this topic warrants continued investigation.",
        "Secondary sources corroborate the primary findings presented here.",
        "In conclusion, the evidence supports a nuanced understanding of the subject.",
    ]

    summary_sentences = sentences[:max_sentences]
    return "Summary:\n" + " ".join(summary_sentences)


# ---------------------------------------------------------------------------
# Fact checking
# ---------------------------------------------------------------------------


async def _fact_check(query: str, options: dict[str, Any]) -> str:
    """Assess the factual accuracy of a claim.

    PRODUCTION INTEGRATION:
    - Use multi-stage fact-checking: web search → LLM reasoning → confidence
    - Cross-reference against trusted sources (Wikipedia, Snopes, PolitiFact API)
    - Return structured verdicts: SUPPORTED, PARTIALLY_SUPPORTED, CONTRADICTED
    - Include source citations and confidence scores

    Example pipeline:
        1. await search_api.get_fact_sources(query)
        2. llm_verdict = await claude.assess_claim(query, sources)
        3. confidence = llm_verdict.confidence_score
        4. return structured_result(verdict, confidence, sources)
    """
    await asyncio.sleep(0.04)

    seed = _deterministic_hash(query)
    # Deterministically assign a verdict based on the hash for reproducibility
    verdict_index = int(seed[:2], 16) % 3
    verdicts = ["SUPPORTED", "PARTIALLY_SUPPORTED", "INSUFFICIENT_EVIDENCE"]
    confidence_values = [0.92, 0.61, 0.38]

    verdict = verdicts[verdict_index]
    confidence = confidence_values[verdict_index]

    sources_checked = 5 + (int(seed[2], 16) % 4)

    return (
        f"Fact-check result for: '{query}'\n\n"
        f"Verdict:     {verdict}\n"
        f"Confidence:  {confidence:.0%}\n"
        f"Sources checked: {sources_checked}\n\n"
        f"Analysis: The claim was evaluated against {sources_checked} independent "
        f"sources. The evidence level is {verdict.lower().replace('_', ' ')} "
        f"with {confidence:.0%} confidence based on available information."
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


_HANDLERS = {
    TaskType.web_research: _web_research,
    TaskType.summarization: _summarize,
    TaskType.fact_checking: _fact_check,
}


async def execute_agent_task(task: AgentTask) -> AgentTaskResult:
    """Route *task* to the appropriate capability handler and return the result.

    Raises:
        ValueError: if task_type is not recognised (should never happen given
                    the Pydantic enum validation, but defensive).
    """
    handler = _HANDLERS.get(task.task_type)
    if handler is None:
        raise ValueError(f"Unknown task type: {task.task_type!r}")

    result_text = await handler(task.query, task.options)

    return AgentTaskResult(
        task_type=task.task_type,
        query=task.query,
        result=result_text,
        metadata={
            "handler": task.task_type.value,
            "options_applied": task.options,
        },
    )
