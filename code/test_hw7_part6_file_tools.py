import os
import tempfile
from pathlib import Path

from hw7_part6_file_tools import (
    SAFE_PREFIXES,
    FileToolError,
    SandboxFileTools,
    confirm_bash,
    is_destructive,
    run_safety_evaluation,
)


def test_six_file_tools_and_short_diff() -> None:
    with tempfile.TemporaryDirectory(prefix="hw7-part6-test-") as temp:
        tools = SandboxFileTools(temp)
        tools.write_file("src/a.py", "DEBUG = False\n")
        assert tools.glob_files("**/*.py")["matches"] == ["src/a.py"]
        assert tools.search_in_files("DEBUG", "**/*.py")["matches"][0]["line"] == 1
        edited = tools.edit_file("src/a.py", "False", "True")
        assert "-DEBUG = False" in edited["diff"]
        assert "+DEBUG = True" in edited["diff"]
        assert tools.read_file("src/a.py", max_lines=1)["content"] == "DEBUG = True\n"
        assert tools.bash("wc -l src/a.py", auto_approve=True)["exit_code"] == 0


def test_integration_requires_glob_search_read() -> None:
    result = run_safety_evaluation()["integration"]
    assert result["required_sequence"] == [
        "glob_files",
        "search_in_files",
        "read_file",
    ]
    assert result["debug_contents_shown"] is True
    assert result["passed"] is True


def test_five_allowed_and_five_blocked() -> None:
    evidence = run_safety_evaluation()
    assert len(evidence["safety_test"]["allowed"]) == 5
    assert len(evidence["safety_test"]["blocked"]) == 5
    assert evidence["safety_test"]["passed_count"] == 10
    assert evidence["all_passed"] is True


def test_destructive_detection_is_independent_of_approval() -> None:
    destructive = [
        "rm -rf .",
        "sudo ls",
        "chmod 777 a.py",
        "dd if=/dev/zero of=/dev/disk9",
        "echo bad > /etc/hw7",
    ]
    for command in destructive:
        assert is_destructive(command) is True
        assert confirm_bash(command, auto_approve=True) is False


def test_safe_prefix_auto_approval_is_bounded() -> None:
    assert set(SAFE_PREFIXES) == {"pwd", "ls", "find", "grep", "wc"}
    assert confirm_bash("ls", auto_approve=True) is True
    assert confirm_bash("python -V", auto_approve=True) is False
    assert confirm_bash("ls", auto_approve=False) is False


def test_path_escape_and_symlink_escape_are_blocked() -> None:
    with tempfile.TemporaryDirectory(prefix="hw7-part6-root-") as temp:
        with tempfile.TemporaryDirectory(prefix="hw7-part6-outside-") as outside:
            tools = SandboxFileTools(temp)
            outside_path = Path(outside) / "secret.txt"
            outside_path.write_text("secret", encoding="utf-8")
            os.symlink(outside_path, Path(temp) / "escape.txt")
            for path in ("../outside.txt", str(outside_path), "escape.txt"):
                try:
                    tools.read_file(path)
                except FileToolError:
                    pass
                else:
                    raise AssertionError(f"sandbox escape accepted: {path}")


def test_shell_operators_and_unconfirmed_commands_are_blocked() -> None:
    with tempfile.TemporaryDirectory(prefix="hw7-part6-test-") as temp:
        tools = SandboxFileTools(temp)
        for command in ("ls; pwd", "python -V"):
            try:
                tools.bash(command, auto_approve=True)
            except FileToolError:
                pass
            else:
                raise AssertionError(f"unsafe command accepted: {command}")


def main() -> int:
    tests = [value for name, value in globals().items() if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS | {test.__name__}")
    print(f"Part 6 file-tool tests: {len(tests)}/{len(tests)} PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
