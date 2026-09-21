from pathlib import Path

from llama_index.core import Document
from llama_index.core.node_parser import (
    SemanticSplitterNodeParser,
    SentenceWindowNodeParser,
    TokenTextSplitter,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding


ROOT = Path(__file__).resolve().parents[1]
WARMUP_FILE = (
    ROOT
    / "corpus"
    / "warmup"
    / "tinyshakespeare.txt"
)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def average_text_length(nodes) -> float:
    if not nodes:
        return 0.0

    total_length = sum(
        len(node.get_content())
        for node in nodes
    )

    return total_length / len(nodes)


def main() -> None:
    warmup_text = WARMUP_FILE.read_text(
        encoding="utf-8"
    )

    # A smaller sample is enough to verify the three chunkers.
    warmup_sample = warmup_text[:20_000]

    document = Document(
        text=warmup_sample,
        metadata={
            "source_file": WARMUP_FILE.name,
            "dataset_type": "warmup_only",
        },
    )

    print(f"Warm-up characters: {len(warmup_sample)}")
    print(f"Embedding model: {MODEL_NAME}")

    embed_model = HuggingFaceEmbedding(
        model_name=MODEL_NAME,
        device="cpu",
    )

    token_splitter = TokenTextSplitter(
        chunk_size=256,
        chunk_overlap=40,
    )

    semantic_splitter = SemanticSplitterNodeParser(
        embed_model=embed_model,
        buffer_size=1,
        breakpoint_percentile_threshold=95,
    )

    sentence_window_splitter = (
        SentenceWindowNodeParser.from_defaults(
            window_size=3,
            window_metadata_key="window",
            original_text_metadata_key="original_text",
        )
    )

    chunkers = {
        "Token": token_splitter,
        "Semantic": semantic_splitter,
        "Sentence-window": sentence_window_splitter,
    }

    for technique_name, chunker in chunkers.items():
        nodes = chunker.get_nodes_from_documents(
            [document]
        )

        print(f"\nTechnique: {technique_name}")
        print(f"Chunks produced: {len(nodes)}")
        print(
            "Average chunk length: "
            f"{average_text_length(nodes):.2f} characters"
        )

        if nodes:
            preview = (
                nodes[0]
                .get_content()
                .replace("\n", " ")[:160]
            )

            print(f"First chunk preview: {preview}")

        if technique_name == "Sentence-window" and nodes:
            window_text = nodes[0].metadata.get(
                "window",
                "",
            )

            print(
                "First window preview: "
                f"{window_text.replace(chr(10), ' ')[:160]}"
            )

    print("\nAll three chunkers passed the warm-up test.")


if __name__ == "__main__":
    main()