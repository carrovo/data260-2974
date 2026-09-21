import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / "corpus" / "hw03"
OUTPUT_FILE = ROOT / "CORPUS_MANIFEST.json"

MINIMUM_CORPUS_BYTES = 200_000


def calculate_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def main() -> None:
    corpus_files = []

    for file_path in sorted(CORPUS_DIR.glob("*.pdf")):
        relative_path = file_path.relative_to(ROOT)

        corpus_files.append(
            {
                "filename": str(relative_path),
                "byte_size": file_path.stat().st_size,
                "sha256": calculate_sha256(file_path),
            }
        )

    total_bytes = sum(
        item["byte_size"]
        for item in corpus_files
    )

    manifest = {
        "domain_id": 6,
        "assigned_domain": "Rental housing listings",
        "minimum_required_bytes": MINIMUM_CORPUS_BYTES,
        "total_bytes": total_bytes,
        "meets_minimum_size": total_bytes >= MINIMUM_CORPUS_BYTES,
        "file_count": len(corpus_files),
        "files": corpus_files,
    }

    OUTPUT_FILE.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(manifest, indent=2))
    print(f"\nSaved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()