"""Run the required ten-query HW9 Part 2 semantic-cache demonstration."""

import asyncio
from statistics import mean

from hw9_config import STUDENT_NAME
from hw9_part2_api import handle_question
from hw9_semantic_cache import SemanticResponseCache

TEST_QUERIES = [
    (
        "new",
        "What information should a renter verify before applying for a rental listing?",
    ),
    (
        "exact duplicate",
        "What information should a renter verify before applying for a rental listing?",
    ),
    (
        "paraphrase",
        "Which details should tenants check before they submit a rental application?",
    ),
    (
        "completely new",
        "What should a renter ask about a security deposit before signing a lease?",
    ),
    (
        "exact duplicate",
        "What should a renter ask about a security deposit before signing a lease?",
    ),
    (
        "paraphrase",
        "Which security-deposit questions should a tenant ask before lease signing?",
    ),
    (
        "completely new",
        "How should a tenant document a maintenance request?",
    ),
    (
        "exact duplicate",
        "How should a tenant document a maintenance request?",
    ),
    (
        "paraphrase",
        "What is the best way for renters to keep records of repair requests?",
    ),
    (
        "exact duplicate",
        "What information should a renter verify before applying for a rental listing?",
    ),
]


async def main() -> None:
    """Clear only semantic entries, execute ten queries, and print measurements."""

    cache = SemanticResponseCache()
    deleted = cache.clear_entries(reset_data_version=True)
    print(f"Student: {STUDENT_NAME}")
    print("=== HW9 Part 2: Semantic Response Cache ===")
    print(f"Threshold: {cache.threshold:.2f}")
    print(f"Previous semantic entries cleared: {deleted}")

    results: list[dict[str, object]] = []
    for query_number, (category, question) in enumerate(TEST_QUERIES, start=1):
        print(f"\nQuery #{query_number} [{category}]")
        print(f"Question: {question}")
        result = await handle_question(question, cache=cache)
        results.append(result)
        print(f"is_cached: {result['is_cached']}")
        print(f"similarity_score: {result['similarity_score']:.4f}")
        print(f"latency_ms: {result['latency_ms']:.2f}")
        print(f"data_version: {result['data_version']}")
        answer = str(result["answer"]).replace("\n", " ")
        print(f"answer_preview: {answer[:180]}")

    cached_latencies = [
        float(result["latency_ms"])
        for result in results
        if result["is_cached"]
    ]
    live_latencies = [
        float(result["latency_ms"])
        for result in results
        if not result["is_cached"]
    ]
    hit_count = len(cached_latencies)
    hit_rate = 100 * hit_count / len(results)

    print("\n=== Part 2 Measurements ===")
    print(f"Total queries: {len(results)}")
    print(f"Cache hits: {hit_count}")
    print(f"Cache misses: {len(live_latencies)}")
    print(f"Cache hit rate: {hit_rate:.1f}%")
    print(
        "Average cached latency: "
        f"{mean(cached_latencies):.2f} ms"
        if cached_latencies
        else "Average cached latency: N/A"
    )
    print(
        "Average non-cached latency: "
        f"{mean(live_latencies):.2f} ms"
        if live_latencies
        else "Average non-cached latency: N/A"
    )
    print("PART2_STATUS: PASS")


if __name__ == "__main__":
    asyncio.run(main())
