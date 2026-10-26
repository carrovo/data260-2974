import argparse
import difflib
import json
import re
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = PROJECT_ROOT / "reports" / "hw07" / "raw" / "part6_safety_results.json"
SAFE_PREFIXES = ("pwd", "ls", "find", "grep", "wc")
MAX_FILE_BYTES = 1_000_000
MAX_OUTPUT_CHARS = 20_000
SHELL_CONTROL_PATTERN = re.compile(r"(?:&&|\|\||[;|`]|\$\()")
ROOT_REDIRECT_PATTERN = re.compile(r"(?:^|\s)\d*(?:>|>>)\s*/")


class FileToolError(ValueError):
    """Raised when a Part 6 file-tool boundary rejects an operation."""


def _tokens(command: str) -> list[str]:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return []
    return tokens


def is_destructive(command: str) -> bool:
    """Return True for destructive shell patterns regardless of approval."""

    tokens = _tokens(command)
    if not tokens:
        return True
    lowered = [token.lower() for token in tokens]
    executable = Path(lowered[0]).name
    if executable in {"sudo", "doas", "su"}:
        return True
    if executable in {"chmod", "chown", "chgrp"}:
        return True
    if executable in {"mkfs", "newfs", "mke2fs", "diskutil"}:
        return True
    if executable == "rm" and any(
        token == "--recursive" or (token.startswith("-") and "r" in token[1:])
        for token in lowered[1:]
    ):
        return True
    if executable == "dd" and any(
        token.startswith("of=/dev/") for token in lowered[1:]
    ):
        return True
    if any(token.startswith("/dev/") for token in lowered):
        return True
    if ROOT_REDIRECT_PATTERN.search(command):
        return True
    if executable == "tee" and any(token.startswith("/") for token in tokens[1:]):
        return True
    return False


def _safe_prefix(command: str) -> bool:
    tokens = _tokens(command)
    return bool(tokens) and Path(tokens[0]).name in SAFE_PREFIXES


def confirm_bash(command: str, auto_approve: bool = False) -> bool:
    """Auto-approve allowlisted non-destructive commands only."""

    if is_destructive(command):
        return False
    return auto_approve and _safe_prefix(command)


class SandboxFileTools:
    """Six bounded file tools rooted in one disposable course sandbox."""

    def __init__(self, sandbox_root: str | Path):
        root = Path(sandbox_root).resolve()
        if not root.is_dir():
            raise FileToolError("sandbox root must be an existing directory")
        self.root = root

    def _resolve(self, relative_path: str, *, must_exist: bool = False) -> Path:
        supplied = Path(relative_path)
        if supplied.is_absolute():
            raise FileToolError("absolute paths are not allowed")
        resolved = (self.root / supplied).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise FileToolError("path escapes the sandbox") from exc
        if must_exist and not resolved.exists():
            raise FileToolError("path does not exist")
        return resolved

    def read_file(self, path: str, max_lines: int = 200) -> dict[str, Any]:
        """Read at most max_lines from one sandboxed UTF-8 file."""

        if not 1 <= max_lines <= 1000:
            raise FileToolError("max_lines must be between 1 and 1000")
        target = self._resolve(path, must_exist=True)
        if not target.is_file() or target.stat().st_size > MAX_FILE_BYTES:
            raise FileToolError("file is unavailable or too large")
        with target.open("r", encoding="utf-8") as handle:
            lines = []
            truncated = False
            for index, line in enumerate(handle):
                if index >= max_lines:
                    truncated = True
                    break
                lines.append(line)
        return {"path": path, "content": "".join(lines), "truncated": truncated}

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        """Write one bounded UTF-8 file below the sandbox root."""

        encoded = content.encode("utf-8")
        if len(encoded) > MAX_FILE_BYTES:
            raise FileToolError("content exceeds the file-size limit")
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
        return {"path": path, "bytes_written": len(encoded)}

    def edit_file(self, path: str, old: str, new: str) -> dict[str, Any]:
        """Replace one exact occurrence and return a bounded unified diff."""

        if not old:
            raise FileToolError("old text must not be empty")
        target = self._resolve(path, must_exist=True)
        original = target.read_text(encoding="utf-8")
        if original.count(old) != 1:
            raise FileToolError("old text must occur exactly once")
        updated = original.replace(old, new, 1)
        if len(updated.encode("utf-8")) > MAX_FILE_BYTES:
            raise FileToolError("edited content exceeds the file-size limit")
        target.write_text(updated, encoding="utf-8")
        diff_lines = list(
            difflib.unified_diff(
                original.splitlines(),
                updated.splitlines(),
                fromfile=path,
                tofile=path,
                lineterm="",
            )
        )
        return {"path": path, "diff": "\n".join(diff_lines[:40])}

    def glob_files(self, pattern: str) -> dict[str, Any]:
        """List sandboxed files matching a relative glob."""

        self._validate_pattern(pattern)
        matches = []
        for match in self.root.glob(pattern):
            resolved = match.resolve()
            try:
                relative = resolved.relative_to(self.root)
            except ValueError:
                continue
            if resolved.is_file():
                matches.append(relative.as_posix())
        return {"pattern": pattern, "matches": sorted(set(matches))[:200]}

    def search_in_files(self, query: str, file_pattern: str) -> dict[str, Any]:
        """Search matching UTF-8 files and return bounded line matches."""

        if not query or len(query) > 500:
            raise FileToolError("query must contain 1 to 500 characters")
        files = self.glob_files(file_pattern)["matches"]
        matches = []
        for relative in files:
            target = self._resolve(relative, must_exist=True)
            if target.stat().st_size > MAX_FILE_BYTES:
                continue
            for line_number, line in enumerate(
                target.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if query in line:
                    matches.append(
                        {"path": relative, "line": line_number, "text": line[:500]}
                    )
                if len(matches) >= 200:
                    return {"query": query, "matches": matches, "truncated": True}
        return {"query": query, "matches": matches, "truncated": False}

    def bash(
        self,
        command: str,
        *,
        approved: bool = False,
        auto_approve: bool = False,
    ) -> dict[str, Any]:
        """Run one non-destructive command in the sandbox without a shell."""

        if not command.strip() or len(command) > 1000:
            raise FileToolError("command must contain 1 to 1000 characters")
        if is_destructive(command):
            raise FileToolError("destructive command blocked")
        if SHELL_CONTROL_PATTERN.search(command):
            raise FileToolError("shell control operators are not allowed")
        if not (approved or confirm_bash(command, auto_approve=auto_approve)):
            raise FileToolError("command requires confirmation")
        tokens = _tokens(command)
        if not tokens:
            raise FileToolError("command could not be parsed")
        completed = subprocess.run(
            tokens,
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return {
            "command": command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[:MAX_OUTPUT_CHARS],
            "stderr": completed.stderr[:MAX_OUTPUT_CHARS],
            "auto_approved": confirm_bash(command, auto_approve=auto_approve),
        }

    @staticmethod
    def _validate_pattern(pattern: str) -> None:
        if not pattern or Path(pattern).is_absolute():
            raise FileToolError("glob pattern must be relative")
        if ".." in Path(pattern).parts:
            raise FileToolError("glob pattern escapes the sandbox")


def _integration_probe(tools: SandboxFileTools) -> dict[str, Any]:
    files = {
        "alpha.py": "MODE = 'INFO'\n",
        "beta.py": "DEBUG = True\nVALUE = 2974\n",
        "gamma.py": "def ready():\n    return True\n",
    }
    for path, content in files.items():
        tools.write_file(path, content)
    sequence = []
    globbed = tools.glob_files("*.py")
    sequence.append("glob_files")
    searched = tools.search_in_files("DEBUG", "*.py")
    sequence.append("search_in_files")
    found_path = searched["matches"][0]["path"]
    read = tools.read_file(found_path, max_lines=10)
    sequence.append("read_file")
    return {
        "required_sequence": sequence,
        "glob_count": len(globbed["matches"]),
        "debug_path": found_path,
        "debug_contents_shown": "DEBUG = True" in read["content"],
        "passed": sequence == ["glob_files", "search_in_files", "read_file"]
        and len(globbed["matches"]) == 3
        and "DEBUG = True" in read["content"],
    }


def run_safety_evaluation() -> dict[str, Any]:
    """Run the required integration flow and five allow/five block probes."""

    allowed = [
        "pwd",
        "ls",
        "find . -maxdepth 1 -type f",
        "grep -n DEBUG beta.py",
        "wc -l beta.py",
    ]
    blocked = [
        "rm -rf .",
        "sudo ls",
        "chmod 777 beta.py",
        "mkfs /dev/test-device",
        "sh -c 'echo owned > /etc/hw7-test'",
    ]
    with tempfile.TemporaryDirectory(prefix="hw7-part6-") as temp:
        tools = SandboxFileTools(temp)
        integration = _integration_probe(tools)
        allow_results = []
        for command in allowed:
            result = tools.bash(command, auto_approve=True)
            allow_results.append(
                {"command": command, "passed": result["exit_code"] == 0}
            )
        block_results = []
        for command in blocked:
            try:
                tools.bash(command, approved=True)
            except FileToolError as exc:
                block_results.append(
                    {"command": command, "passed": True, "reason": str(exc)}
                )
            else:
                block_results.append(
                    {"command": command, "passed": False, "reason": "executed"}
                )
    all_passed = (
        integration["passed"]
        and all(item["passed"] for item in allow_results)
        and all(item["passed"] for item in block_results)
    )
    return {
        "status": "completed_part6_file_tool_evaluation",
        "sandbox": "temporary_course_sandbox",
        "safe_prefixes": list(SAFE_PREFIXES),
        "integration": integration,
        "safety_test": {
            "allowed": allow_results,
            "blocked": block_results,
            "passed_count": sum(item["passed"] for item in allow_results)
            + sum(item["passed"] for item in block_results),
            "total_count": len(allow_results) + len(block_results),
        },
        "all_passed": all_passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run HW7 Part 6 file-tool tests")
    parser.add_argument("--write-evidence", action="store_true")
    args = parser.parse_args()
    evidence = run_safety_evaluation()
    if args.write_evidence:
        DEFAULT_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_EVIDENCE.write_text(
            json.dumps(evidence, indent=2) + "\n",
            encoding="utf-8",
        )
    print("HW7 Part 6 | FILE TOOLS AND BASH SAFETY")
    print("INTEGRATION | glob -> search -> read | " + (
        "PASS" if evidence["integration"]["passed"] else "FAIL"
    ))
    for item in evidence["safety_test"]["allowed"]:
        print(f"ALLOW | {item['command']} | {'PASS' if item['passed'] else 'FAIL'}")
    for item in evidence["safety_test"]["blocked"]:
        print(f"BLOCK | {item['command']} | {'PASS' if item['passed'] else 'FAIL'}")
    print(
        "SAFETY_TOTAL: "
        f"{evidence['safety_test']['passed_count']}/"
        f"{evidence['safety_test']['total_count']} PASS"
    )
    return 0 if evidence["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
