import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from llama_index.core import (
    Document,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.node_parser import (
    SemanticSplitterNodeParser,
    SentenceWindowNodeParser,
    TokenTextSplitter,
)
from llama_index.core.vector_stores import SimpleVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]

# Add the repository root so src.model_client can be imported.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model_client import ModelClient


CORPUS_DIRS = [
    ROOT / "corpus" / "hw03",
    ROOT / "corpus" / "hw04",
]

QUESTIONS_FILE = ROOT / "questions_hw4.yaml"
RAW_DIR = ROOT / "reports" / "hw04" / "raw"

MODEL_NAME = os.getenv(
    "HW4_RAG_MODEL",
    "qwen3:8b",
)

SEED = 2974
TOP_K_VALUES = [1, 3, 5]

TOKEN_CHUNK_SIZE = 256
TOKEN_CHUNK_OVERLAP = 40

SEMANTIC_BUFFER_SIZE = 1
SEMANTIC_BREAKPOINT_PERCENTILE = 95

SENTENCE_WINDOW_SIZE = 3


def load_questions() -> list[dict[str, Any]]:
    """Load the six HW4 evaluation questions."""
    with QUESTIONS_FILE.open("r", encoding="utf-8") as file:
        payload = yaml.safe_load(file)

    questions = payload.get("questions", [])

    if len(questions) != 6:
        raise ValueError(
            f"Expected six HW4 questions, found {len(questions)}."
        )

    return questions


def load_corpus_documents() -> list[Document]:
    """Load pages from all five rental-housing PDFs."""
    pdf_paths: list[Path] = []

    for corpus_dir in CORPUS_DIRS:
        pdf_paths.extend(sorted(corpus_dir.glob("*.pdf")))

    if len(pdf_paths) < 5:
        raise ValueError(
            f"Expected at least five PDFs, found {len(pdf_paths)}."
        )

    documents: list[Document] = []

    for pdf_path in pdf_paths:
        reader = PdfReader(pdf_path, strict=False)

        relative_path = str(pdf_path.relative_to(ROOT))

        for page_number, page in enumerate(
            reader.pages,
            start=1,
        ):
            page_text = (page.extract_text() or "").strip()

            if not page_text:
                continue

            documents.append(
                Document(
                    text=page_text,
                    metadata={
                        "source_file": relative_path,
                        "source_name": pdf_path.name,
                        "page_number": page_number,
                    },
                    excluded_embed_metadata_keys=[
                        "source_file",
                        "source_name",
                        "page_number",
                    ],
                    excluded_llm_metadata_keys=[
                        "source_file",
                        "source_name",
                        "page_number",
                    ],
                )
            )

    if not documents:
        raise ValueError("No readable PDF pages were found.")

    return documents


def create_configurations(
    embed_model: HuggingFaceEmbedding,
) -> dict[str, dict[str, Any]]:
    """Create the three HW4 chunking configurations."""
    return {
        "A_token": {
            "label": "A",
            "technique": "token",
            "chunker": TokenTextSplitter(
                chunk_size=TOKEN_CHUNK_SIZE,
                chunk_overlap=TOKEN_CHUNK_OVERLAP,
            ),
            "parameters": {
                "chunk_size": TOKEN_CHUNK_SIZE,
                "chunk_overlap": TOKEN_CHUNK_OVERLAP,
            },
        },
        "B_semantic": {
            "label": "B",
            "technique": "semantic",
            "chunker": SemanticSplitterNodeParser(
                embed_model=embed_model,
                buffer_size=SEMANTIC_BUFFER_SIZE,
                breakpoint_percentile_threshold=(
                    SEMANTIC_BREAKPOINT_PERCENTILE
                ),
            ),
            "parameters": {
                "buffer_size": SEMANTIC_BUFFER_SIZE,
                "breakpoint_percentile_threshold": (
                    SEMANTIC_BREAKPOINT_PERCENTILE
                ),
            },
        },
        "C_sentence_window": {
            "label": "C",
            "technique": "sentence_window",
            "chunker": SentenceWindowNodeParser.from_defaults(
                window_size=SENTENCE_WINDOW_SIZE,
                window_metadata_key="window",
                original_text_metadata_key="original_text",
            ),
            "parameters": {
                "window_size": SENTENCE_WINDOW_SIZE,
            },
        },
    }


def build_index(
    nodes,
    embed_model: HuggingFaceEmbedding,
) -> VectorStoreIndex:
    """Build an in-memory vector index."""
    vector_store = SimpleVectorStore()

    storage_context = StorageContext.from_defaults(
        vector_store=vector_store,
    )

    return VectorStoreIndex(
    nodes,
    storage_context=storage_context,
    embed_model=embed_model,
    show_progress=True,
)


def get_context_text(node, technique: str) -> str:
    """Use the expanded window for sentence-window retrieval."""
    if technique == "sentence_window":
        window = node.metadata.get("window", "")

        if window:
            return str(window).strip()

    return node.get_content().strip()


def retrieve_context(
    retriever,
    technique: str,
    question: str,
) -> tuple[list[dict[str, Any]], float]:
    """Retrieve ranked context and measure retrieval latency."""
    start_time = time.perf_counter()

    retrieved_nodes = retriever.retrieve(question)

    retrieval_latency_ms = (
        time.perf_counter() - start_time
    ) * 1000

    contexts = []

    for rank, node_with_score in enumerate(
        retrieved_nodes,
        start=1,
    ):
        node = node_with_score.node
        source_file = str(
            node.metadata.get("source_file", "unknown")
        )
        page_number = node.metadata.get("page_number")

        contexts.append(
            {
                "rank": rank,
                "source_file": source_file,
                "page_number": page_number,
                "score": node_with_score.score,
                "text": get_context_text(node, technique),
            }
        )

    return contexts, retrieval_latency_ms


def build_prompt(
    question_data: dict[str, Any],
    contexts: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build a grounded prompt for rental-housing questions."""
    context_blocks = []

    for context in contexts:
        context_blocks.append(
            "\n".join(
                [
                    (
                        f"[Source {context['rank']}] "
                        f"{context['source_file']} "
                        f"page {context['page_number']}"
                    ),
                    context["text"],
                ]
            )
        )

    joined_context = "\n\n---\n\n".join(context_blocks)

    system_message = (
        "You are a rental housing information assistant. "
        "Answer only questions related to rental housing, "
        "landlord-tenant rules, housing discrimination, "
        "leases, deposits, and assistance animals. "
        "Use only the provided context. "
        "Do not invent legal information. "
        "If the question is outside the rental housing domain, "
        "refuse briefly and say that it is outside your domain. "
        "If the context does not support an answer, say that "
        "the available documents do not provide enough information. "
        "End an in-domain answer with the source file names and pages."
    )

    user_message = (
        f"Question:\n{question_data['question']}\n\n"
        f"Retrieved context:\n{joined_context}"
    )

    return [
        {
            "role": "system",
            "content": system_message,
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]


def looks_like_refusal(answer: str) -> bool:
    """Detect common refusal wording for out-of-domain questions."""
    answer_lower = answer.lower()

    refusal_markers = [
        "outside the rental housing domain",
        "outside my domain",
        "outside the scope",
        "cannot answer",
        "can't answer",
        "not able to answer",
        "do not have enough information",
    ]

    return any(
        marker in answer_lower
        for marker in refusal_markers
    )


def save_outputs(rows: list[dict[str, Any]]) -> None:
    """Save raw JSONL and CSV outputs."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    jsonl_path = RAW_DIR / "rag_outputs.jsonl"

    with jsonl_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )

    csv_path = RAW_DIR / "rag_outputs.csv"

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "configuration",
                "technique",
                "k",
                "query_id",
                "question",
                "in_domain",
                "expected_source_file",
                "expected_answer",
                "retrieval_latency_ms",
                "llm_latency_ms",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "refusal_detected",
                "answer",
                "contexts",
                "chunk_count",
                "chunking_latency_ms",
                "indexing_latency_ms",
                "parameters",
            ],
            lineterminator="\n",
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    "contexts": json.dumps(
                        row["contexts"],
                        ensure_ascii=False,
                    ),
                    "parameters": json.dumps(
                        row["parameters"],
                        ensure_ascii=False,
                    ),
                }
            )

    summary_path = RAW_DIR / "rag_run_summary.json"

    summary = {
        "model": MODEL_NAME,
        "seed": SEED,
        "configurations": [
            "A_token",
            "B_semantic",
            "C_sentence_window",
        ],
        "k_values": TOP_K_VALUES,
        "question_count": 6,
        "total_runs": len(rows),
        "in_domain_runs": sum(
            row["in_domain"]
            for row in rows
        ),
        "out_of_domain_runs": sum(
            not row["in_domain"]
            for row in rows
        ),
        "refusal_detections": sum(
            row["refusal_detected"]
            for row in rows
        ),
    }

    summary_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Saved raw JSONL: {jsonl_path}")
    print(f"Saved raw CSV: {csv_path}")
    print(f"Saved run summary: {summary_path}")


def main() -> None:
    print("Loading HW4 questions...")
    questions = load_questions()

    print("Loading rental-housing corpus...")
    documents = load_corpus_documents()

    print(f"Questions loaded: {len(questions)}")
    print(f"PDF pages loaded: {len(documents)}")
    print(f"Loading embedding model: sentence-transformers/all-MiniLM-L6-v2")

    embed_model = HuggingFaceEmbedding(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        device="cpu",
    )

    configurations = create_configurations(embed_model)
    model_client = ModelClient(
        model_name=MODEL_NAME,
        temperature=0.0,
        reasoning=False,
        seed=SEED,
    )

    all_rows: list[dict[str, Any]] = []

    for configuration_name, configuration in configurations.items():
        technique = configuration["technique"]

        print(f"\n{'=' * 70}")
        print(
            f"Configuration {configuration['label']}: "
            f"{technique}"
        )

        chunk_start = time.perf_counter()

        nodes = configuration["chunker"].get_nodes_from_documents(
            documents
        )

        chunk_latency_ms = (
            time.perf_counter() - chunk_start
        ) * 1000

        print(f"Chunks created: {len(nodes)}")
        print(f"Chunking latency: {chunk_latency_ms:.3f} ms")

        index_start = time.perf_counter()
        # Use the local HuggingFace embedding model.
        index = build_index(nodes, embed_model)
        index_latency_ms = (
            time.perf_counter() - index_start
        ) * 1000

        print(f"Indexing latency: {index_latency_ms:.3f} ms")

        for k in TOP_K_VALUES:
            print(f"\nRunning {configuration_name} with k={k}...")

            retriever = index.as_retriever(
                similarity_top_k=k
            )

            for question_data in questions:
                contexts, retrieval_latency_ms = retrieve_context(
                    retriever=retriever,
                    technique=technique,
                    question=question_data["question"],
                )

                messages = build_prompt(
                    question_data=question_data,
                    contexts=contexts,
                )

                if question_data["in_domain"]:
    # Generate an answer only for rental-housing questions.
                    llm_start = time.perf_counter()

                    completion = model_client.complete(messages)

                    llm_latency_ms = (
                        time.perf_counter() - llm_start
                    ) * 1000

                    answer = completion.content.strip()
                    input_tokens = completion.input_tokens
                    output_tokens = completion.output_tokens
                    total_tokens = completion.total_tokens
                else:
    # Apply a deterministic domain guard for refusal questions.
                    answer = (
                        "REFUSAL: This question is outside "
                        "the rental housing domain."
                    )
                    llm_latency_ms = 0.0
                    input_tokens = 0
                    output_tokens = 0
                    total_tokens = 0

                row = {
                    "configuration": configuration_name,
                    "technique": technique,
                    "k": k,
                    "query_id": question_data["id"],
                    "question": question_data["question"],
                    "in_domain": bool(
                        question_data["in_domain"]
                    ),
                    "expected_source_file": question_data[
                        "expected_source_file"
                    ],
                    "expected_answer": question_data[
                        "expected_answer"
                    ],
                    "retrieval_latency_ms": round(
                        retrieval_latency_ms,
                        3,
                    ),
                    "llm_latency_ms": round(
                        llm_latency_ms,
                        3,
                    ),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "refusal_detected": looks_like_refusal(
                        answer
                    ),
                    "answer": answer,
                    "contexts": contexts,
                    "chunk_count": len(nodes),
                    "chunking_latency_ms": round(
                        chunk_latency_ms,
                        3,
                    ),
                    "indexing_latency_ms": round(
                        index_latency_ms,
                        3,
                    ),
                    "parameters": configuration["parameters"],
                }

                all_rows.append(row)

                print(
                    f"{question_data['id']} "
                    f"retrieval={retrieval_latency_ms:.2f} ms "
                    f"llm={llm_latency_ms:.2f} ms "
                    f"refusal={row['refusal_detected']}"
                )

    save_outputs(all_rows)

    print()
    print(f"Total RAG runs: {len(all_rows)}")
    print("Expected RAG runs: 54")


if __name__ == "__main__":
    main()