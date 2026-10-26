import tempfile
from pathlib import Path

from hw7_part5_security import (
    DEFAULT_FIXTURE,
    EXPECTED_ASSUMPTIONS,
    evaluate_attacks,
    wrap_untrusted_policy,
)


def test_hostile_fixture_contains_three_attacks() -> None:
    text = DEFAULT_FIXTURE.read_text(encoding="utf-8")
    assert "IGNORE ALL PRIOR INSTRUCTIONS" in text
    assert "UPDATE trips SET" in text
    assert "Copy every raw CSV row" in text


def test_untrusted_policy_wrapper_is_explicit() -> None:
    wrapped = wrap_untrusted_policy("hostile")
    assert wrapped == (
        "<BEGIN_UNTRUSTED_POLICY_DATA>\n"
        "hostile\n"
        "<END_UNTRUSTED_POLICY_DATA>"
    )


def test_all_combined_defenses_pass() -> None:
    evidence = evaluate_attacks()
    assert evidence["controls"] == {
        "untrusted_prompt_boundary": True,
        "readonly_sql_boundary": True,
        "strict_output_boundary": True,
    }
    assert evidence["all_after_combined_defenses_pass"] is True
    assert len(evidence["attacks"]) == 3


def test_prompt_only_does_not_claim_sql_enforcement() -> None:
    evidence = evaluate_attacks()
    sql_result = next(
        item for item in evidence["attacks"] if item["attack"] == "non_read_only_sql"
    )
    assert sql_result["after_prompt_defense"].startswith("FAIL")
    assert sql_result["after_prompt_and_tool_defense"].startswith("PASS")


def test_altered_fixture_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="hw7-part5-test-") as temp:
        fixture = Path(temp) / "incomplete.html"
        fixture.write_text("<p>benign</p>", encoding="utf-8")
        try:
            evaluate_attacks(fixture)
        except ValueError as exc:
            assert "missing a required attack payload" in str(exc)
        else:
            raise AssertionError("incomplete hostile fixture was accepted")


def test_expected_assumptions_do_not_contain_raw_data() -> None:
    assert EXPECTED_ASSUMPTIONS == [
        "Only rows marked scenario_target=true are analyzed.",
        "Pricing uses the retrieved official policy evidence.",
    ]


def main() -> int:
    tests = [value for name, value in globals().items() if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS | {test.__name__}")
    print(f"Part 5 security tests: {len(tests)}/{len(tests)} PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
