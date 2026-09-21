from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / "corpus" / "hw03"


def main() -> None:
    pdf_files = sorted(CORPUS_DIR.glob("*.pdf"))

    if not pdf_files:
        raise FileNotFoundError(
            f"No PDF files found in {CORPUS_DIR}"
        )

    total_characters = 0

    for file_path in pdf_files:
        reader = PdfReader(file_path)

        page_text = [
            page.extract_text() or ""
            for page in reader.pages
        ]

        character_count = sum(
            len(text)
            for text in page_text
        )

        total_characters += character_count

        print(
            f"{file_path.name}: "
            f"pages={len(reader.pages)}, "
            f"text_characters={character_count}"
        )

        if character_count < 100:
            raise ValueError(
                f"Too little text was extracted from {file_path.name}"
            )

    print(f"\nFiles checked: {len(pdf_files)}")
    print(f"Total extracted characters: {total_characters}")
    print("Corpus text extraction check passed.")


if __name__ == "__main__":
    main()