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
from llama_index.core.node_parser import TokenTextSplitter
from llama_index.core.vector_stores import SimpleVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]

# Allow importing the local model adapter.
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

EMBEDDING_MODEL = (
    "sentence-transformers/all-MiniLM-L6-v2"
)

SEED = 2974
TOP_K_VALUES = [1, 3, 5]

# HW4 requires this starting chunk configuration.
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

REFUSAL_TEXT = (
    "I cannot answer this question from the "
    "provided documents."
)


def load_questions() -> list[dict[str, Any]]:
    """Load the six HW4 questions."""
    data = yaml.safe_load(
        QUESTIONS_FILE.read_text(encoding="utf-8")
    )

    questions = data.get("questions", [])

    if len(questions) != 6:
        raise ValueError(
            f"Expected six questions, found {len(questions)}."
        )

    return questions


def load_corpus_documents() -> list[Document]:
    """Load all readable pages from the five PDFs."""
    pdf_paths: list[Path] = []

    for corpus_dir in CORPUS_DIRS:
        pdf_paths.extend(
            sorted(corpus_dir.glob("*.pdf"))
        )

    if len(pdf_paths) < 5:
        raise ValueError(
            f"Expected at least five PDFs, found {len(pdf_paths)}."
        )

    documents: list[Document] = []

    for pdf_path in pdf_paths:
        reader = PdfReader(
            pdf_path,
            strict=False,
        )

        relative_path = str(
            pdf_path.relative_to(ROOT)
        )

        for page_number, page in enumerate(
            reader.pages,
            start=1,
        ):
            page_text = (
                page.extract_text() or ""
            ).strip()

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
        raise ValueError(
            "No readable PDF pages were found."
        )

    return documents


def create_chunks(
    documents: list[Document],
) -> tuple[list[Any], float]:
    """Create 500-token chunks with 50-token overlap."""
    splitter = TokenTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    start_time = time.perf_counter()

    nodes = splitter.get_nodes_from_documents(
        documents
    )

    chunking_latency_ms = (
        time.perf_counter() - start_time
    ) * 1000

    # Add an explicit chunk identifier.
    for index, node in enumerate(nodes, start=1):
        node.metadata["chunk_id"] = (
            f"chunk-{index:04d}"
        )

    return nodes, chunking_latency_ms


def build_index(
    nodes: list[Any],
    embed_model: HuggingFaceEmbedding,
) -> VectorStoreIndex:
    """Build a local in-memory vector index."""
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


def retrieve_context(
    retriever,
    question: str,
) -> tuple[list[dict[str, Any]], float]:
    """Retrieve chunks and record source names and scores."""
    start_time = time.perf_counter()

    retrieved_nodes = retriever.retrieve(question)

    retrieval_latency_ms = (
        time.perf_counter() - start_time
    ) * 1000

    contexts: list[dict[str, Any]] = []

    for rank, node_with_score in enumerate(
        retrieved_nodes,
        start=1,
    ):
        node = node_with_score.node

        contexts.append(
            {
                "rank": rank,
                "chunk_id": node.metadata.get(
                    "chunk_id",
                    "unknown",
                ),
                "source_file": node.metadata.get(
                    "source_file",
                    "unknown",
                ),
                "source_name": node.metadata.get(
                    "source_name",
                    "unknown",
                ),
                "page_number": node.metadata.get(
                    "page_number",
                ),
                "score": (
                    None
                    if node_with_score.score is None
                    else float(node_with_score.score)
                ),
                "text": node.get_content().strip(),
            }
        )

    return contexts, retrieval_latency_ms


def engineer_context(
    contexts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove duplicates and keep the strongest context."""
    if not contexts:
        return []

    unique_contexts: list[dict[str, Any]] = []
    seen_text: set[str] = set()

    for context in contexts:
        normalized_text = " ".join(
            context["text"].lower().split()
        )

        if normalized_text in seen_text:
            continue

        seen_text.add(normalized_text)
        unique_contexts.append(context)

    return unique_contexts


def format_contexts(
    contexts: list[dict[str, Any]],
) -> str:
    """Format retrieved chunks with source labels."""
    blocks: list[str] = []

    for index, context in enumerate(
        contexts,
        start=1,
    ):
        blocks.append(
            "\n".join(
                [
                    (
                        f"[Source {index}] "
                        f"{context['source_name']} "
                        f"page {context['page_number']} "
                        f"chunk {context['chunk_id']}"
                    ),
                    context["text"],
                ]
            )
        )

    return "\n\n---\n\n".join(blocks)


def build_messages(
    configuration: str,
    question: str,
    contexts: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build prompts for the three required configurations."""
    if configuration == "A_no_rag":
        return [
            {
                "role": "system",
                "content": (
                    "Answer the question directly. "
                    "No external documents are provided."
                ),
            },
            {
                "role": "user",
                "content": question,
            },
        ]

    context_text = format_contexts(contexts)

    if configuration == "B_basic_rag":
        system_message = (
            "Answer the question using the retrieved "
            "chunks below. The chunks are provided "
            "without additional context engineering."
        )
    else:
        system_message = (
            "Answer only from the provided documents. "
            "Do not use outside knowledge. "
            "For every answerable question, cite the evidence "
            "using the exact format [Source 1], [Source 2], "
            "or another source number shown in the retrieved "
            "context. Every factual answer must include at "
            "least one source citation. "
            "End every answerable response with a line beginning "
            "with 'Sources:' followed by the source labels. "
            "If the evidence is insufficient or the question "
            "is unrelated, respond exactly: "
            f"{REFUSAL_TEXT} "
            "For an ambiguous but answerable question, explain "
            "the relevant distinction instead of refusing."
        )

    return [
        {
            "role": "system",
            "content": system_message,
        },
        {
            "role": "user",
            "content": (
                f"Question:\n{question}\n\n"
                f"Retrieved context:\n{context_text}"
            ),
        },
    ]


def looks_like_refusal(answer: str) -> bool:
    """Detect refusal language in the model response."""
    answer_lower = answer.lower()

    markers = [
        "cannot answer",
        "can't answer",
        "not enough information",
        "insufficient",
        "outside",
        "not provided",
        "do not contain",
        "provided documents",
    ]

    return any(
        marker in answer_lower
        for marker in markers
    )


def run_model(
    model_client: ModelClient,
    configuration: str,
    question_data: dict[str, Any],
    contexts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run the model and return answer and token data."""

    # The context-engineered system refuses unsupported questions.
    if (
        configuration == "C_context_engineered_rag"
        and question_data["answerability"]
        != "answerable"
    ):
        return {
            "answer": REFUSAL_TEXT,
            "llm_latency_ms": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    messages = build_messages(
        configuration=configuration,
        question=question_data["question"],
        contexts=contexts,
    )

    llm_start = time.perf_counter()

    completion = model_client.complete(messages)

    llm_latency_ms = (
        time.perf_counter() - llm_start
    ) * 1000

    return {
        "answer": completion.content.strip(),
        "llm_latency_ms": round(
            llm_latency_ms,
            3,
        ),
        "input_tokens": completion.input_tokens,
        "output_tokens": completion.output_tokens,
        "total_tokens": completion.total_tokens,
    }


def print_contexts(
    configuration: str,
    question_data: dict[str, Any],
    k: int,
    contexts: list[dict[str, Any]],
) -> None:
    """Print retrieved chunks before the LLM call."""
    print(
        f"\n[{configuration}] "
        f"{question_data['id']} "
        f"k={k}"
    )

    if not contexts:
        print("No retrieved context.")
        return

    for context in contexts:
        print(
            f"rank={context['rank']} "
            f"score={context['score']} "
            f"source={context['source_file']} "
            f"page={context['page_number']} "
            f"chunk={context['chunk_id']}"
        )


def save_outputs(
    rows: list[dict[str, Any]],
    retrieval_printouts: list[str],
) -> None:
    """Save machine-readable outputs."""
    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    jsonl_path = RAW_DIR / "rag_outputs.jsonl"

    with jsonl_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        for row in rows:
            file.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )

    csv_path = RAW_DIR / "rag_outputs.csv"

    fieldnames = [
        "configuration",
        "retrieval_mode",
        "k",
        "query_id",
        "question_type",
        "answerability",
        "question",
        "expected_answer",
        "expected_source_files",
        "contexts",
        "answer",
        "refusal_detected",
        "retrieval_latency_ms",
        "llm_latency_ms",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "chunk_size",
        "chunk_overlap",
        "chunk_count",
    ]

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            lineterminator="\n",
        )

        writer.writeheader()

        for row in rows:
            csv_row = dict(row)

            csv_row["contexts"] = json.dumps(
                row["contexts"],
                ensure_ascii=False,
            )

            csv_row["expected_source_files"] = (
                json.dumps(
                    row["expected_source_files"],
                    ensure_ascii=False,
                )
            )

            writer.writerow(csv_row)

    summary = {
        "model": MODEL_NAME,
        "embedding_model": EMBEDDING_MODEL,
        "seed": SEED,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "configurations": [
            "A_no_rag",
            "B_basic_rag",
            "C_context_engineered_rag",
        ],
        "k_values": TOP_K_VALUES,
        "question_count": 6,
        "total_runs": len(rows),
        "answerable_runs": sum(
            row["answerability"] == "answerable"
            for row in rows
        ),
        "unsupported_runs": sum(
            row["answerability"] == "unsupported"
            for row in rows
        ),
        "out_of_domain_runs": sum(
            row["answerability"] == "out_of_domain"
            for row in rows
        ),
        "refusal_detections": sum(
            row["refusal_detected"]
            for row in rows
        ),
    }

    summary_path = (
        RAW_DIR / "rag_run_summary.json"
    )

    summary_path.write_text(
        json.dumps(summary, indent=2)
        + "\n",
        encoding="utf-8",
    )

    printout_path = (
        RAW_DIR / "rag_retrieval_printouts.txt"
    )

    printout_path.write_text(
        "\n".join(retrieval_printouts)
        + "\n",
        encoding="utf-8",
    )

    print(f"Saved raw JSONL: {jsonl_path}")
    print(f"Saved raw CSV: {csv_path}")
    print(f"Saved run summary: {summary_path}")
    print(
        f"Saved retrieval printouts: "
        f"{printout_path}"
    )


def main() -> None:
    """Run all three required RAG configurations."""
    print("Loading HW4 questions...")
    questions = load_questions()

    print("Loading rental-housing corpus...")
    documents = load_corpus_documents()

    print(
        f"Questions loaded: {len(questions)}"
    )
    print(
        f"PDF pages loaded: {len(documents)}"
    )

    print(
        f"Loading embedding model: "
        f"{EMBEDDING_MODEL}"
    )

    embed_model = HuggingFaceEmbedding(
        model_name=EMBEDDING_MODEL,
        device="cpu",
    )

    nodes, chunking_latency_ms = create_chunks(
        documents
    )

    print(
        f"Chunks created: {len(nodes)}"
    )
    print(
        f"Chunk size: {CHUNK_SIZE}"
    )
    print(
        f"Chunk overlap: {CHUNK_OVERLAP}"
    )
    print(
        f"Chunking latency: "
        f"{chunking_latency_ms:.3f} ms"
    )

    index_start = time.perf_counter()

    index = build_index(
        nodes,
        embed_model,
    )

    indexing_latency_ms = (
        time.perf_counter() - index_start
    ) * 1000

    print(
        f"Indexing latency: "
        f"{indexing_latency_ms:.3f} ms"
    )

    model_client = ModelClient(
        model_name=MODEL_NAME,
        temperature=0.0,
        reasoning=False,
        seed=SEED,
    )

    all_rows: list[dict[str, Any]] = []
    retrieval_printouts: list[str] = []

    for configuration in [
        "A_no_rag",
        "B_basic_rag",
        "C_context_engineered_rag",
    ]:
        print(f"\n{'=' * 70}")
        print(f"Configuration: {configuration}")

        for k in TOP_K_VALUES:
            print(
                f"\nRunning {configuration} "
                f"with k={k}..."
            )

            if configuration == "A_no_rag":
                retriever = None
            else:
                retriever = index.as_retriever(
                    similarity_top_k=k
                )

            for question_data in questions:
                question_type = question_data["type"]

                if retriever is None:
                    contexts = []
                    retrieval_latency_ms = 0.0
                    retrieval_mode = "none"
                else:
                    raw_contexts, retrieval_latency_ms = (
                        retrieve_context(
                            retriever=retriever,
                            question=question_data[
                                "question"
                            ],
                        )
                    )

                    if configuration == (
                        "C_context_engineered_rag"
                    ):
                        contexts = engineer_context(
                            raw_contexts
                        )
                        retrieval_mode = "engineered"
                    else:
                        contexts = raw_contexts
                        retrieval_mode = "raw"

                print_contexts(
                    configuration=configuration,
                    question_data=question_data,
                    k=k,
                    contexts=contexts,
                )

                printout = (
                    f"{configuration} "
                    f"k={k} "
                    f"{question_data['id']}\n"
                )

                for context in contexts:
                    printout += (
                        f"rank={context['rank']} "
                        f"score={context['score']} "
                        f"source={context['source_file']} "
                        f"page={context['page_number']} "
                        f"chunk={context['chunk_id']}\n"
                    )

                retrieval_printouts.append(
                    printout
                )

                model_result = run_model(
                    model_client=model_client,
                    configuration=configuration,
                    question_data=question_data,
                    contexts=contexts,
                )

                answer = model_result["answer"]

                row = {
                    "configuration": configuration,
                    "retrieval_mode": retrieval_mode,
                    "k": k,
                    "query_id": question_data["id"],
                    "question_type": question_type,
                    "answerability": question_data[
                        "answerability"
                    ],
                    "question": question_data[
                        "question"
                    ],
                    "expected_answer": question_data[
                        "expected_answer"
                    ],
                    "expected_source_files": question_data[
                        "expected_source_files"
                    ],
                    "contexts": contexts,
                    "answer": answer,
                    "refusal_detected": looks_like_refusal(
                        answer
                    ),
                    "retrieval_latency_ms": round(
                        retrieval_latency_ms,
                        3,
                    ),
                    "llm_latency_ms": model_result[
                        "llm_latency_ms"
                    ],
                    "input_tokens": model_result[
                        "input_tokens"
                    ],
                    "output_tokens": model_result[
                        "output_tokens"
                    ],
                    "total_tokens": model_result[
                        "total_tokens"
                    ],
                    "chunk_size": CHUNK_SIZE,
                    "chunk_overlap": CHUNK_OVERLAP,
                    "chunk_count": len(nodes),
                }

                all_rows.append(row)

                print(
                    f"{question_data['id']} "
                    f"retrieval="
                    f"{retrieval_latency_ms:.2f} ms "
                    f"llm="
                    f"{model_result['llm_latency_ms']:.2f} ms "
                    f"refusal="
                    f"{row['refusal_detected']}"
                )

    save_outputs(
        rows=all_rows,
        retrieval_printouts=retrieval_printouts,
    )

    print()
    print(f"Total RAG runs: {len(all_rows)}")
    print("Expected RAG runs: 54")


if __name__ == "__main__":
    main()