import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "hw02"
VERIFY_FILE = REPORT_DIR / "verification.json"
TEMP_DIR = ROOT / "tmp" / "hw02_verify"

PORT_BASE = 8274
SID4 = 2974
SEED = 2974
VERIFY_SEED = 262974
MODEL = "qwen3:8b"
TAG_NAME = "hw2-final"

checks = []


def add_check(name, passed, details):
    checks.append(
        {
            "name": name,
            "passed": bool(passed),
            "details": details,
        }
    )


def run_command(command, timeout=120):
    return subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def get_git_commit(reference):
    result = run_command(
        ["git", "rev-parse", f"{reference}^{{commit}}"],
        timeout=15,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


head_commit = get_git_commit("HEAD")
tag_commit = get_git_commit(TAG_NAME)

add_check(
    "final_tag_points_to_head",
    bool(tag_commit) and tag_commit == head_commit,
    f"Tag: {TAG_NAME}; tag commit: {tag_commit}; HEAD: {head_commit}",
)

compile_result = run_command(
    [
        sys.executable,
        "-m",
        "py_compile",
        "code/main.py",
        "code/hw2_graph_demo.py",
        "code/hw2_experiment_runner.py",
        "src/model_client.py",
        "src/hw2_graph/state.py",
        "src/hw2_graph/nodes.py",
        "src/hw2_graph/router.py",
        "src/hw2_graph/workflow.py",
        "src/hw2_graph/schemas.py",
    ]
)

add_check(
    "python_files_compile",
    compile_result.returncode == 0,
    compile_result.stderr.strip() or "All Python files compiled.",
)

server = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--app-dir",
        str(ROOT / "code"),
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT_BASE),
    ],
    cwd=ROOT,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

api_passed = False
api_details = "FastAPI did not respond before the timeout."

try:
    for _ in range(30):
        if server.poll() is not None:
            api_details = "The FastAPI process stopped unexpectedly."
            break

        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{PORT_BASE}/api/listings",
                timeout=2,
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
                api_passed = response.status == 200 and isinstance(data, list)
                api_details = (
                    f"HTTP {response.status}; response is a list: "
                    f"{isinstance(data, list)}"
                )
                break
        except Exception:
            time.sleep(1)
finally:
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

add_check("fastapi_responds_on_port_8274", api_passed, api_details)

TEMP_DIR.mkdir(parents=True, exist_ok=True)

graph_result = run_command(
    [
        sys.executable,
        "code/hw2_experiment_runner.py",
        "--input",
        "reports/hw02/cases/schema_input.json",
        "--experiment",
        "verification",
        "--runs",
        "1",
        "--max-turns",
        "2",
        "--output-stem",
        "verification_run",
        "--raw-dir",
        str(TEMP_DIR),
        "--seed",
        str(VERIFY_SEED),
    ],
    timeout=180,
)

add_check(
    "langgraph_smoke_test_finishes",
    graph_result.returncode == 0,
    (
        "Experiment runner finished successfully."
        if graph_result.returncode == 0
        else graph_result.stderr.strip()
    ),
)

three_tags_passed = False
tag_details = "No readable verification result was produced."

result_file = TEMP_DIR / "verification_run.json"

if result_file.exists():
    payload = json.loads(result_file.read_text(encoding="utf-8"))
    runs = payload.get("runs") or payload.get("results") or []

    if runs:
        first_run = runs[0]
        tags = first_run.get("tags", [])
        three_tags_passed = (
            first_run.get("status") == "completed"
            and isinstance(tags, list)
            and len(tags) == 3
        )
        tag_details = (
            f"Status: {first_run.get('status')}; "
            f"number of tags: {len(tags) if isinstance(tags, list) else 0}"
        )

add_check(
    "planner_returns_exactly_three_tags",
    three_tags_passed,
    tag_details,
)

verification = {
    "homework": "HW2",
    "sid4": SID4,
    "commit_hash": tag_commit or head_commit,
    "tag": TAG_NAME,
    "model_configuration": {
        "model": MODEL,
        "temperature": 0.0,
    },
    "seed": SEED,
    "verify_seed": VERIFY_SEED,
    "checks": checks,
    "overall_pass": all(check["passed"] for check in checks),
}

REPORT_DIR.mkdir(parents=True, exist_ok=True)
VERIFY_FILE.write_text(
    json.dumps(verification, indent=2) + "\n",
    encoding="utf-8",
)

print(json.dumps(verification, indent=2))
print(f"\nSaved to: {VERIFY_FILE}")

sys.exit(0 if verification["overall_pass"] else 1)