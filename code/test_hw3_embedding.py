import numpy as np

from llama_index.embeddings.huggingface import HuggingFaceEmbedding


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def main() -> None:
    print(f"Loading embedding model: {MODEL_NAME}")

    embed_model = HuggingFaceEmbedding(
        model_name=MODEL_NAME,
        device="cpu",
    )

    test_query = "What rights do California tenants have?"

    query_embedding = embed_model.get_query_embedding(
        test_query
    )

    query_vector = np.array(
        query_embedding,
        dtype=np.float32,
    )

    print(f"Test query: {test_query}")
    print(f"Embedding dimension: {len(query_embedding)}")
    print(f"Query vector shape: {query_vector.shape}")
    print(
        "First 8 values:",
        [
            round(float(value), 6)
            for value in query_embedding[:8]
        ],
    )

    if len(query_embedding) != 384:
        raise ValueError(
            "Expected all-MiniLM-L6-v2 to return "
            "a 384-dimensional embedding."
        )

    print("Embedding model check passed.")


if __name__ == "__main__":
    main()