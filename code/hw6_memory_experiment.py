import argparse
import csv
import json
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "reports" / "hw06" / "raw"
PROBES_PATH = ROOT / "memory_probes.yaml"
METRICS_PATH = ROOT / "reports" / "hw06" / "METRICS.md"
RUN_LOG_PATH = ROOT / "reports" / "hw06" / "RUN_LOG.txt"


CONVERSATION = [
    "I am beginning a rental search for later this year.",
    "My original maximum monthly rent budget was $2,400.",
    "At first I was considering Santa Clara.",
    "I work near downtown and want a manageable commute.",
    "I prefer an apartment rather than a detached house.",
    "At the beginning of the search I did not have a pet.",
    "Natural light would be helpful but is not mandatory.",
    "Please keep explanations concise when comparing listings.",
    "I would like a quiet building when possible.",
    "My original target move-in date was November 1, 2026.",
    "A one-bedroom unit is enough for me.",
    "I do not want a shared room.",
    "Parking is useful but not an absolute requirement.",
    "I prefer listings with clear monthly cost information.",
    "The rental must have in-unit laundry.",
    "Please prioritize verified details over guesses.",
    "I can tour apartments on weekend afternoons.",
    "A gym is optional and should not outweigh the budget.",
    "I prefer a lease of about twelve months.",
    "Update: San Jose is now my preferred city, not Santa Clara.",
    "I now have one indoor cat, so the rental must allow cats.",
    "Update: my current maximum monthly rent budget is $2,200.",
    "Do not recommend anything above my current budget.",
    "My commute preference is secondary to affordability.",
    "I still need in-unit laundry in the final recommendation.",
    "Update: my current target move-in date is November 15, 2026.",
    "Please treat the newer date as replacing the original date.",
    "Please treat newer preference updates as authoritative.",
    "Summarize constraints when they affect a recommendation.",
    "Remember my current rental constraints for later questions.",
]

SETTINGS = [
    {
        "name": "SHORT_TERM_N=4",
        "short_term_n": 4,
        "policy": "standard",
    },
    {
        "name": "SHORT_TERM_N=12",
        "short_term_n": 12,
        "policy": "standard",
    },
    {
        "name": "SHORT_TERM_N=30",
        "short_term_n": 30,
        "policy": "standard",
    },
    {
        "name": "Importance eviction (N=12)",
        "short_term_n": 12,
        "policy": "importance_eviction",
    },
]


def load_probes() -> list[dict[str, Any]]:
    data = yaml.safe_load(PROBES_PATH.read_text(encoding="utf-8"))
    probes = data.get("probes", [])

    if len(probes) != 5:
        raise ValueError(f"Expected five probes, found {len(probes)}")

    return probes


def score_probe(answer: str, probe: dict[str, Any]) -> int:
    normalized = " ".join(answer.casefold().split())
    correct = any(
        str(term).casefold() in normalized for term in probe.get("expected_any", [])
    )
    conflict = any(
        str(term).casefold() in normalized for term in probe.get("forbidden_any", [])
    )

    if correct and not conflict:
        return 5

    if correct and conflict:
        return 3

    uncertainty_markers = (
        "not sure",
        "do not know",
        "don't know",
        "cannot determine",
    )

    if any(marker in normalized for marker in uncertainty_markers):
        return 2

    return 1


def post_chat(
    base_url: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=300,
        ) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST /api/chat returned {exc.code}: {body[:600]}") from exc


def run_setting(
    base_url: str,
    setting: dict[str, Any],
    probes: list[dict[str, Any]],
    run_stamp: str,
    turn_delay: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    slug = (
        setting["name"]
        .lower()
        .replace("=", "-")
        .replace(" ", "-")
        .replace("(", "")
        .replace(")", "")
    )
    user_id = f"hw6-{run_stamp}-{slug}"
    session_id = f"session-{slug}"
    turn_records: list[dict[str, Any]] = []

    for turn_number, message in enumerate(CONVERSATION, start=1):
        result = post_chat(
            base_url,
            {
                "user_id": user_id,
                "session_id": session_id,
                "message": message,
                "memory_mode": "mongodb",
                "short_term_n": setting["short_term_n"],
                "policy": setting["policy"],
            },
        )
        turn_records.append(
            {
                "setting": setting["name"],
                "stage": "conversation",
                "turn_number": turn_number,
                "user_id": user_id,
                "session_id": session_id,
                "message": message,
                "reply": result["reply"],
                **result["metrics"],
            }
        )
        print(f"{setting['name']} conversation {turn_number:02d}/30 complete")

        if turn_delay:
            time.sleep(turn_delay)

    probe_records: list[dict[str, Any]] = []

    for probe_number, probe in enumerate(probes, start=1):
        result = post_chat(
            base_url,
            {
                "user_id": user_id,
                "session_id": session_id,
                "message": probe["question"],
                "memory_mode": "mongodb",
                "short_term_n": setting["short_term_n"],
                "policy": setting["policy"],
            },
        )
        score = score_probe(result["reply"], probe)
        record = {
            "setting": setting["name"],
            "stage": "probe",
            "turn_number": 30 + probe_number,
            "probe_id": probe["id"],
            "question": probe["question"],
            "answer": result["reply"],
            "score": score,
            "expected_any": probe.get("expected_any", []),
            "forbidden_any": probe.get("forbidden_any", []),
            **result["metrics"],
        }
        probe_records.append(record)
        turn_records.append(record)
        print(f"{setting['name']} probe {probe_number}/5: score={score}")

        if turn_delay:
            time.sleep(turn_delay)

    return turn_records, probe_records


def estimated_conversation_cost(
    mean_input_tokens: float,
    mean_output_tokens: float,
) -> float:
    conversations = 10_000
    turns = 30
    input_cost = (mean_input_tokens * turns * conversations / 1_000_000) * 1.0
    output_cost = (mean_output_tokens * turns * conversations / 1_000_000) * 5.0
    return input_cost + output_cost


def summarize_setting(
    setting: dict[str, Any],
    turn_records: list[dict[str, Any]],
    probe_records: list[dict[str, Any]],
) -> dict[str, Any]:
    conversation_records = [
        record for record in turn_records if record["stage"] == "conversation"
    ]
    mean_prompt = statistics.mean(
        float(record["prompt_tokens"]) for record in conversation_records
    )
    mean_input = statistics.mean(
        float(record.get("total_input_tokens", record["prompt_tokens"]))
        for record in conversation_records
    )
    mean_output = statistics.mean(
        float(
            record.get(
                "total_output_tokens",
                record["completion_tokens"],
            )
        )
        for record in conversation_records
    )
    mean_latency = statistics.mean(
        float(record["latency_ms"]) for record in conversation_records
    )
    probe_quality = statistics.mean(float(record["score"]) for record in probe_records)

    return {
        "setting": setting["name"],
        "short_term_n": setting["short_term_n"],
        "policy": setting["policy"],
        "mean_prompt_tokens_per_turn": round(mean_prompt, 3),
        "mean_total_input_tokens_per_turn": round(mean_input, 3),
        "mean_total_output_tokens_per_turn": round(mean_output, 3),
        "mean_latency_ms": round(mean_latency, 3),
        "mean_probe_quality": round(probe_quality, 3),
        "estimated_cost_10000_30_turn_conversations_usd": round(
            estimated_conversation_cost(mean_input, mean_output),
            2,
        ),
    }


def write_outputs(
    turns: list[dict[str, Any]],
    probes: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    (RAW_DIR / "short_term_sweep_turns.json").write_text(
        json.dumps(turns, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (RAW_DIR / "memory_probe_results.json").write_text(
        json.dumps(probes, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (RAW_DIR / "memory_experiment_summary.json").write_text(
        json.dumps(summaries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    with (RAW_DIR / "short_term_sweep_turns.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as output:
        fieldnames = [
            "setting",
            "stage",
            "turn_number",
            "prompt_tokens",
            "completion_tokens",
            "total_input_tokens",
            "total_output_tokens",
            "latency_ms",
            "score",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for record in turns:
            writer.writerow({name: record.get(name, "") for name in fieldnames})

    baseline = next(row for row in summaries if row["setting"] == "SHORT_TERM_N=12")
    policy = next(
        row for row in summaries if row["setting"] == "Importance eviction (N=12)"
    )
    savings = (
        1
        - policy["mean_prompt_tokens_per_turn"]
        / baseline["mean_prompt_tokens_per_turn"]
    ) * 100
    comparison = {
        "baseline": baseline,
        "policy": policy,
        "prompt_token_savings_percent": round(savings, 3),
        "probe_quality_change": round(
            policy["mean_probe_quality"] - baseline["mean_probe_quality"],
            3,
        ),
    }
    (RAW_DIR / "eviction_comparison.json").write_text(
        json.dumps(comparison, indent=2),
        encoding="utf-8",
    )

    highest_quality = max(row["mean_probe_quality"] for row in summaries)
    acceptable = [
        row for row in summaries if row["mean_probe_quality"] >= highest_quality - 0.5
    ]
    best = min(
        acceptable,
        key=lambda row: row["estimated_cost_10000_30_turn_conversations_usd"],
    )
    worst = max(
        summaries,
        key=lambda row: row["estimated_cost_10000_30_turn_conversations_usd"],
    )
    cost_payload = {
        "pricing": {
            "input_per_million_tokens_usd": 1,
            "output_per_million_tokens_usd": 5,
            "conversation_count": 10000,
            "turns_per_conversation": 30,
        },
        "selection_rule": (
            "Best is the lowest-cost setting within 0.5 points of "
            "the highest probe-quality score. Worst is the "
            "highest-cost measured setting."
        ),
        "best": best,
        "worst": worst,
    }
    (RAW_DIR / "memory_costs.json").write_text(
        json.dumps(cost_payload, indent=2),
        encoding="utf-8",
    )

    table_rows = "\n".join(
        "| "
        f"{row['setting']} | "
        f"{row['mean_prompt_tokens_per_turn']:.3f} | "
        f"{row['mean_latency_ms']:.3f} | "
        f"{row['mean_probe_quality']:.3f} |"
        for row in summaries
    )
    METRICS_PATH.write_text(
        "# HW6 Metrics\n\n"
        "| Setting | Mean prompt tokens/turn | Mean latency (ms) "
        "| Probe quality (1-5) |\n"
        "|---|---:|---:|---:|\n"
        f"{table_rows}\n\n"
        "## Eviction comparison\n\n"
        f"Prompt-token savings: {savings:.3f}%  \n"
        "Probe-quality change: "
        f"{comparison['probe_quality_change']:.3f}\n\n"
        "## Cost estimate\n\n"
        f"Best: {best['setting']} - "
        f"${best['estimated_cost_10000_30_turn_conversations_usd']:.2f}  \n"
        f"Worst: {worst['setting']} - "
        f"${worst['estimated_cost_10000_30_turn_conversations_usd']:.2f}\n\n"
        f"Selection rule: {cost_payload['selection_rule']}\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the controlled DATA 260 HW6 memory experiment."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8274",
    )
    parser.add_argument(
        "--turn-delay",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate fixtures without calling the API.",
    )
    args = parser.parse_args()
    probes = load_probes()

    if len(CONVERSATION) != 30:
        raise ValueError(f"Expected 30 conversation turns, found {len(CONVERSATION)}")

    if args.dry_run:
        print("PASS: 30 fixed conversation turns")
        print("PASS: 5 fixed memory probes")
        print("PASS: 4 controlled settings")
        return

    run_stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    all_turns: list[dict[str, Any]] = []
    all_probes: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    for setting in SETTINGS:
        turns, probe_results = run_setting(
            args.base_url,
            setting,
            probes,
            run_stamp,
            args.turn_delay,
        )
        all_turns.extend(turns)
        all_probes.extend(probe_results)
        summaries.append(summarize_setting(setting, turns, probe_results))

    write_outputs(all_turns, all_probes, summaries)

    completed = datetime.now().astimezone().isoformat()
    with RUN_LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(f"\n[{completed}] HW6 memory experiment completed.\n")

        for summary in summaries:
            log.write(json.dumps(summary) + "\n")

    print(json.dumps(summaries, indent=2))
    print(f"Wrote results to {RAW_DIR}")


if __name__ == "__main__":
    main()
