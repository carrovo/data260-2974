import csv
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
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
CORPUS_DIR = ROOT / "corpus" / "hw03"
QUESTIONS_FILE = ROOT / "questions.yaml"
RAW_DIR = ROOT / "reports" / "hw03" / "raw"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 5

TOKEN_CHUNK_SIZE = 256
TOKEN_CHUNK_OVERLAP = 40

SEMANTIC_BUFFER_SIZE = 1
SEMANTIC_BREAKPOINT_PERCENTILE = 95

SENTENCE_WINDOW_SIZE = 3


def load_questions() -> list[dict[str, Any]]:
    with QUESTIONS_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        payload = yaml.safe_load(file)

    questions = payload.get("questions", [])

    if len(questions) < 5:
        raise ValueError(
            "questions.yaml must contain at least five questions."
        )

    return questions


def load_corpus_documents() -> list[Document]:
    documents: list[Document] = []

    pdf_files = sorted(CORPUS_DIR.glob("*.pdf"))

    if not pdf_files:
        raise FileNotFoundError(
            f"No PDF files found in {CORPUS_DIR}"
        )

    for pdf_path in pdf_files:
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
            page_text = page.extract_text() or ""
            page_text = page_text.strip()

            if not page_text:
                continue

            metadata = {
                "source_file": relative_path,
                "source_name": pdf_path.name,
                "page_number": page_number,
            }

            document = Document(
                text=page_text,
                metadata=metadata,
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

            documents.append(document)

    if not documents:
        raise ValueError(
            "The corpus did not produce any readable documents."
        )

    return documents


def create_chunkers(
    embed_model: HuggingFaceEmbedding,
) -> dict[str, Any]:
    token_splitter = TokenTextSplitter(
        chunk_size=TOKEN_CHUNK_SIZE,
        chunk_overlap=TOKEN_CHUNK_OVERLAP,
    )

    semantic_splitter = SemanticSplitterNodeParser(
        embed_model=embed_model,
        buffer_size=SEMANTIC_BUFFER_SIZE,
        breakpoint_percentile_threshold=(
            SEMANTIC_BREAKPOINT_PERCENTILE
        ),
    )

    sentence_window_splitter = (
        SentenceWindowNodeParser.from_defaults(
            window_size=SENTENCE_WINDOW_SIZE,
            window_metadata_key="window",
            original_text_metadata_key="original_text",
        )
    )

    return {
        "token": token_splitter,
        "semantic": semantic_splitter,
        "sentence_window": sentence_window_splitter,
    }





def calculate_cosine_similarity(
    vector_a: np.ndarray,
    vector_b: np.ndarray,
) -> float:
    denominator = (
        np.linalg.norm(vector_a)
        * np.linalg.norm(vector_b)
    )

    if denominator == 0:
        return 0.0

    return float(
        np.dot(vector_a, vector_b)
        / denominator
    )


def get_retrieved_text(
    node,
    technique_name: str,
) -> str:
    if technique_name == "sentence_window":
        window_text = node.metadata.get(
            "window",
            "",
        )

        if window_text:
            return str(window_text).strip()

    return node.get_content().strip()


def build_vector_index(
    nodes,
    embed_model: HuggingFaceEmbedding,
) -> VectorStoreIndex:
    vector_store = SimpleVectorStore()

    storage_context = StorageContext.from_defaults(
        vector_store=vector_store,
    )

    index = VectorStoreIndex(
        nodes,
        storage_context=storage_context,
        embed_model=embed_model,
        show_progress=True,
    )

    return index


def retrieve_for_question(
    technique_name: str,
    question_data: dict[str, Any],
    retriever,
    embed_model: HuggingFaceEmbedding,
) -> dict[str, Any]:
    question_id = question_data["id"]
    question_text = question_data["question"]
    expected_source = question_data[
        "expected_source_file"
    ]

    query_embedding = embed_model.get_query_embedding(
        question_text
    )

    query_vector = np.array(
        query_embedding,
        dtype=np.float32,
    )

    retrieval_start = time.perf_counter()

    retrieved_nodes = retriever.retrieve(
        question_text
    )

    retrieval_latency_ms = (
        time.perf_counter() - retrieval_start
    ) * 1000

    result_rows: list[dict[str, Any]] = []
    document_vectors: list[np.ndarray] = []

    for rank, node_with_score in enumerate(
        retrieved_nodes,
        start=1,
    ):
        node = node_with_score.node
        indexed_text = node.get_content().strip()

        retrieved_text = get_retrieved_text(
            node,
            technique_name,
        )

        document_embedding = (
            embed_model.get_text_embedding(
                retrieved_text
            )
        )

        document_vector = np.array(
            document_embedding,
            dtype=np.float32,
        )

        document_vectors.append(document_vector)

        cosine_similarity = (
            calculate_cosine_similarity(
                query_vector,
                document_vector,
            )
        )

        source_file = str(
            node.metadata.get(
                "source_file",
                "unknown",
            )
        )

        page_number = node.metadata.get(
            "page_number"
        )

        preview = " ".join(
            retrieved_text.split()
        )[:160]

        store_score = node_with_score.score

        result_rows.append(
            {
                "rank": rank,
                "store_score": (
                    None
                    if store_score is None
                    else float(store_score)
                ),
                "cosine_sim": cosine_similarity,
                "chunk_len": len(indexed_text),
                "context_len": len(retrieved_text),
                "preview": preview,
                "source_file": source_file,
                "page_number": page_number,
                "source_match": (
                    source_file == expected_source
                ),
            }
        )

    if document_vectors:
        document_matrix = np.vstack(
            document_vectors
        )
    else:
        document_matrix = np.empty(
            (0, len(query_vector)),
            dtype=np.float32,
        )

    query_payload = {
        "technique": technique_name,
        "query_id": question_id,
        "query": question_text,
        "expected_answer": question_data[
            "expected_answer"
        ],
        "expected_source_file": expected_source,
        "embedding_model": MODEL_NAME,
        "embedding_dimension": len(
            query_embedding
        ),
        "query_embedding_first_8": [
            float(value)
            for value in query_embedding[:8]
        ],
        "query_vector_shape": list(
            query_vector.shape
        ),
        "document_vectors_shape": list(
            document_matrix.shape
        ),
        "retrieval_latency_ms": (
            retrieval_latency_ms
        ),
        "top_k": TOP_K,
        "results": result_rows,
    }

    print(
        f"\nTechnique: {technique_name}"
    )
    print(
        f"Query ID: {question_id}"
    )
    print(
        f"Query: {question_text}"
    )
    print(
        "Embedding dimension: "
        f"{len(query_embedding)}"
    )
    print(
        "First 8 query embedding values: "
        f"{query_payload['query_embedding_first_8']}"
    )
    print(
        "Query vector shape: "
        f"{query_vector.shape}"
    )
    print(
        "Stacked document vector shape: "
        f"{document_matrix.shape}"
    )
    print(
        "Retrieval latency: "
        f"{retrieval_latency_ms:.3f} ms"
    )

    display_columns = [
        "rank",
        "store_score",
        "cosine_sim",
        "chunk_len",
        "context_len",
        "source_file",
        "page_number",
        "source_match",
        "preview",
    ]

    result_table = pd.DataFrame(
        result_rows
    )

    if not result_table.empty:
        print(
            result_table[
                display_columns
            ].to_string(
                index=False,
                float_format=lambda value: (
                    f"{value:.6f}"
                ),
            )
        )

    return query_payload

def save_query_payload(
    query_payload: dict[str, Any],
) -> None:
    technique_name = query_payload["technique"]
    question_id = query_payload["query_id"]

    output_file = RAW_DIR / (
        f"{technique_name}_{question_id}.json"
    )

    output_file.write_text(
        json.dumps(
            query_payload,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def flatten_query_payloads(
    query_payloads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    flattened_rows: list[dict[str, Any]] = []

    for payload in query_payloads:
        for result in payload["results"]:
            flattened_rows.append(
                {
                    "technique": payload[
                        "technique"
                    ],
                    "query_id": payload[
                        "query_id"
                    ],
                    "query": payload["query"],
                    "expected_source_file": payload[
                        "expected_source_file"
                    ],
                    "embedding_model": payload[
                        "embedding_model"
                    ],
                    "embedding_dimension": payload[
                        "embedding_dimension"
                    ],
                    "query_embedding_first_8": (
                        json.dumps(
                            payload[
                                "query_embedding_first_8"
                            ]
                        )
                    ),
                    "query_vector_shape": (
                        json.dumps(
                            payload[
                                "query_vector_shape"
                            ]
                        )
                    ),
                    "document_vectors_shape": (
                        json.dumps(
                            payload[
                                "document_vectors_shape"
                            ]
                        )
                    ),
                    "retrieval_latency_ms": payload[
                        "retrieval_latency_ms"
                    ],
                    **result,
                }
            )

    return flattened_rows


def save_combined_outputs(
    query_payloads: list[dict[str, Any]],
) -> None:
    jsonl_file = (
        RAW_DIR
        / "retrieval_results.jsonl"
    )

    with jsonl_file.open(
        "w",
        encoding="utf-8",
    ) as file:
        for payload in query_payloads:
            file.write(
                json.dumps(payload) + "\n"
            )

    flattened_rows = flatten_query_payloads(
        query_payloads
    )

    csv_file = (
        RAW_DIR
        / "retrieval_results.csv"
    )

    pd.DataFrame(
        flattened_rows
    ).to_csv(
        csv_file,
        index=False,
    )

    print(f"Saved combined JSONL: {jsonl_file}")
    print(f"Saved combined CSV: {csv_file}")


def main() -> None:
    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("Loading evaluation questions...")
    questions = load_questions()

    print("Loading formal PDF corpus...")
    documents = load_corpus_documents()

    print(
        f"Questions loaded: {len(questions)}"
    )
    print(
        f"Readable PDF pages loaded: {len(documents)}"
    )

    print(
        f"Loading embedding model: {MODEL_NAME}"
    )

    embed_model = HuggingFaceEmbedding(
        model_name=MODEL_NAME,
        device="cpu",
    )

    chunkers = create_chunkers(
        embed_model
    )

    all_query_payloads: list[
        dict[str, Any]
    ] = []

    chunking_statistics: list[
        dict[str, Any]
    ] = []

    technique_parameters = {
        "token": {
            "chunk_size": TOKEN_CHUNK_SIZE,
            "chunk_overlap": TOKEN_CHUNK_OVERLAP,
        },
        "semantic": {
            "buffer_size": SEMANTIC_BUFFER_SIZE,
            "breakpoint_percentile_threshold": (
                SEMANTIC_BREAKPOINT_PERCENTILE
            ),
        },
        "sentence_window": {
            "window_size": SENTENCE_WINDOW_SIZE,
        },
    }

    for technique_name, chunker in (
        chunkers.items()
    ):
        print(
            "\n"
            + "=" * 80
        )
        print(
            f"Creating chunks for: "
            f"{technique_name}"
        )

        chunking_start = time.perf_counter()

        nodes = (
            chunker.get_nodes_from_documents(
                documents
            )
        )

        chunking_latency_ms = (
            time.perf_counter()
            - chunking_start
        ) * 1000

        chunk_lengths = [
            len(node.get_content())
            for node in nodes
        ]

        average_chunk_length = (
            float(np.mean(chunk_lengths))
            if chunk_lengths
            else 0.0
        )

        print(
            f"Chunks produced: {len(nodes)}"
        )
        print(
            "Average indexed chunk length: "
            f"{average_chunk_length:.2f} "
            "characters"
        )
        print(
            "Chunking time: "
            f"{chunking_latency_ms:.3f} ms"
        )

        print(
            f"Building in-memory index for: "
            f"{technique_name}"
        )

        indexing_start = time.perf_counter()

        index = build_vector_index(
            nodes,
            embed_model,
        )

        indexing_latency_ms = (
            time.perf_counter()
            - indexing_start
        ) * 1000

        print(
            "Indexing time: "
            f"{indexing_latency_ms:.3f} ms"
        )

        retriever = index.as_retriever(
            similarity_top_k=TOP_K
        )

        chunking_statistics.append(
            {
                "technique": technique_name,
                "chunks": len(nodes),
                "avg_chunk_length_chars": (
                    average_chunk_length
                ),
                "chunking_latency_ms": (
                    chunking_latency_ms
                ),
                "indexing_latency_ms": (
                    indexing_latency_ms
                ),
                "parameters": technique_parameters[
                    technique_name
                ],
            }
        )

        for question_data in questions:
            query_payload = (
                retrieve_for_question(
                    technique_name=(
                        technique_name
                    ),
                    question_data=(
                        question_data
                    ),
                    retriever=retriever,
                    embed_model=embed_model,
                )
            )

            save_query_payload(
                query_payload
            )

            all_query_payloads.append(
                query_payload
            )

    chunk_stats_file = (
        RAW_DIR
        / "chunking_statistics.json"
    )

    chunk_stats_file.write_text(
        json.dumps(
            chunking_statistics,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    save_combined_outputs(
        all_query_payloads
    )

    print(
        f"Saved chunking statistics: "
        f"{chunk_stats_file}"
    )
    print(
        f"Query-technique runs completed: "
        f"{len(all_query_payloads)}"
    )
    print(
        "Formal retrieval experiment completed."
    )


if __name__ == "__main__":
    main()