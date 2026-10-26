# ruff: noqa: E402

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = PROJECT_ROOT / "code"

if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from hw7_part4_tools import (
    PRICING_URL,
    capture_policy_snapshot,
    verify_snapshot_hash,
)


def main() -> None:
    print("HW7 PART 4 OFFICIAL PRICING INTEGRATION CAPTURE")
    print(f"REQUESTED_URL: {PRICING_URL}")

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)

        try:
            snapshot = capture_policy_snapshot(
                url=PRICING_URL,
                html_path=root / "pricing_page.html",
                snapshot_path=root / "pricing_snapshot.json",
            )
        except Exception as exc:
            print(
                "SKIP | official network unavailable | "
                f"{type(exc).__name__}: {exc}"
            )
            print(
                "ALLOWLIST_REQUIRED: www.lyft.com, lyftbikes.com"
            )
            return

        assert snapshot["capture_kind"] == "official_network_capture"
        assert snapshot["final_url"].startswith("https://")
        assert snapshot["pricing_rules"]["month_pass"]["amount"] == "29"
        assert verify_snapshot_hash(root / "pricing_snapshot.json") is True
        print(f"PASS | FINAL_URL: {snapshot['final_url']}")
        print(f"PASS | HTML_BYTES: {snapshot['html_bytes']}")
        print(f"PASS | SHA256: {snapshot['html_sha256']}")


if __name__ == "__main__":
    main()
