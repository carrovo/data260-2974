import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_PATH = (
    REPOSITORY_ROOT
    / "reports"
    / "hw01"
    / "verification.json"
)

checks: list[dict[str, object]] = []


def add_check(
    name: str,
    passed: bool,
    details: str
) -> None:
    """Add one verification result."""
    checks.append(
        {
            "name": name,
            "passed": passed,
            "details": details
        }
    )


required_files = [
    "README.md",
    "DOMAIN_SCHEMA.md",
    "AGENT.md",
    "requirements.txt",
    "code/Dockerfile",
    "code/web_application/index.html",
    "code/web_application/feedback.js",
    "code/agents_demo.py",
    "code/experiment_runner.py",
    "code/hw1_client.py",
    "src/model_client.py",
    "reports/hw01/RUN_LOG.txt",
    "reports/hw01/METRICS.md",
    "reports/hw01/AI_USE.md",
    "reports/hw01/reproducible_run_instructions.md",
    "reports/hw01/raw/nondeterminism_runs.json",
    "reports/hw01/raw/token_counts.json"
]

missing_files = [
    path
    for path in required_files
    if not (REPOSITORY_ROOT / path).is_file()
]

add_check(
    name="required_files",
    passed=not missing_files,
    details=(
        "All required files are present."
        if not missing_files
        else f"Missing files: {missing_files}"
    )
)


experiment_path = (
    REPOSITORY_ROOT
    / "reports"
    / "hw01"
    / "raw"
    / "nondeterminism_runs.json"
)

try:
    experiment_data = json.loads(
        experiment_path.read_text(encoding="utf-8")
    )

    runs = experiment_data["runs"]

    temperature_zero_count = sum(
        record["temperature"] == 0.0
        for record in runs
    )

    temperature_point_seven_count = sum(
        record["temperature"] == 0.7
        for record in runs
    )

    experiment_passed = (
        len(runs) == 40
        and temperature_zero_count == 20
        and temperature_point_seven_count == 20
    )

    add_check(
        name="nondeterminism_experiment",
        passed=experiment_passed,
        details=(
            f"Total runs: {len(runs)}; "
            f"temperature 0.0: {temperature_zero_count}; "
            f"temperature 0.7: {temperature_point_seven_count}."
        )
    )

except Exception as error:
    add_check(
        name="nondeterminism_experiment",
        passed=False,
        details=f"Could not validate experiment data: {error}"
    )


token_path = (
    REPOSITORY_ROOT
    / "reports"
    / "hw01"
    / "raw"
    / "token_counts.json"
)

try:
    token_data = json.loads(
        token_path.read_text(encoding="utf-8")
    )

    token_turns = token_data["turns"]
    final_total = token_data["checkpoints"][
        "afterTurn5"
    ]["cumulativeTotalTokens"]

    token_passed = (
        token_data["turnCount"] == 5
        and len(token_turns) == 5
        and final_total == 2619
        and all(
            turn["bulletOnlyPass"]
            for turn in token_turns
        )
    )

    add_check(
        name="token_accounting",
        passed=token_passed,
        details=(
            f"Turns: {len(token_turns)}; "
            f"final cumulative tokens: {final_total}."
        )
    )

except Exception as error:
    add_check(
        name="token_accounting",
        passed=False,
        details=f"Could not validate token data: {error}"
    )


adapter_path = REPOSITORY_ROOT / "src" / "model_client.py"
agents_path = REPOSITORY_ROOT / "code" / "agents_demo.py"
client_path = REPOSITORY_ROOT / "code" / "hw1_client.py"

adapter_text = adapter_path.read_text(encoding="utf-8")
agents_text = agents_path.read_text(encoding="utf-8")
client_text = client_path.read_text(encoding="utf-8")

adapter_passed = (
    "def complete(" in adapter_text
    and "ChatOllama" in adapter_text
    and "ChatOllama" not in agents_text
    and "ChatOllama" not in client_text
    and ".invoke(" not in agents_text
    and ".invoke(" not in client_text
    and "ModelClient" in agents_text
    and "ModelClient" in client_text
)

add_check(
    name="model_adapter",
    passed=adapter_passed,
    details=(
        "Application model calls use src/model_client.py."
        if adapter_passed
        else "A direct model call was found outside the adapter."
    )
)


agent_text = (
    REPOSITORY_ROOT / "AGENT.md"
).read_text(encoding="utf-8")

agent_passed = (
    "bullet" in agent_text.lower()
    and '- "' in agent_text
)

add_check(
    name="agent_instructions",
    passed=agent_passed,
    details=(
        "AGENT.md contains bullet-only response instructions."
        if agent_passed
        else "Bullet-only instructions were not detected."
    )
)


try:
    with urlopen(
        "http://localhost:8274",
        timeout=5
    ) as response:
        page = response.read().decode("utf-8")
        status = response.status

    web_passed = (
        status == 200
        and "Rental Housing Listings" in page
    )

    add_check(
        name="docker_web_application",
        passed=web_passed,
        details=(
            f"HTTP status: {status}; "
            "expected page heading detected."
        )
    )

except Exception as error:
    add_check(
        name="docker_web_application",
        passed=False,
        details=f"Could not access localhost:8274: {error}"
    )


verification = {
    "generatedAt": datetime.now(
        timezone.utc
    ).isoformat(),
    "sid4": "2974",
    "portBase": 8274,
    "model": "qwen3:8b",
    "overallPassed": all(
        bool(check["passed"])
        for check in checks
    ),
    "checks": checks
}

OUTPUT_PATH.write_text(
    json.dumps(
        verification,
        indent=2,
        ensure_ascii=False
    ),
    encoding="utf-8"
)

print(
    json.dumps(
        verification,
        indent=2,
        ensure_ascii=False
    )
)

if not verification["overallPassed"]:
    sys.exit(1)