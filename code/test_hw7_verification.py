import json

from verify_hw7 import build_verification


def test_current_hw7_evidence_passes() -> None:
    result = build_verification()
    assert result["homework"] == 7
    assert result["sid4"] == 2974
    assert result["seed"] == 2974
    assert result["verify_seed"] == 262974
    assert result["model"] == "qwen3:8b"
    assert len(result["commit_hash"]) == 40
    assert result["passed"] is True
    assert all(check["passed"] for check in result["checks"])
    json.dumps(result)


def main() -> int:
    test_current_hw7_evidence_passes()
    print("PASS | current HW7 evidence")
    print("HW7 verification tests: 1/1 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
