
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np


class HybridRetriever:
    def __init__(self, documents):
        self.documents = documents

        self.embedder = SentenceTransformer(
            "BAAI/bge-small-en-v1.5"
        )

        self.tokens = [
            doc["text"].lower().split()
            for doc in documents
        ]

        self.bm25 = BM25Okapi(self.tokens)

        embeddings = self.embedder.encode(
            [doc["text"] for doc in documents],
            normalize_embeddings=True
        )

        self.index = faiss.IndexFlatIP(
            len(embeddings[0])
        )

        self.index.add(
            np.array(
                embeddings,
                dtype="float32"
            )
        )

    def search(self, query, top_k=5):
        bm25_scores = self.bm25.get_scores(
            query.lower().split()
        )

        bm25_ranked = sorted(
            zip(self.documents, bm25_scores),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]

        query_embedding = self.embedder.encode(
            [query],
            normalize_embeddings=True
        )

        scores, ids = self.index.search(
            np.array(query_embedding, dtype="float32"),
            top_k
        )

        vector_results = []

        for idx in ids[0]:
            if idx >= 0:
                vector_results.append(
                    self.documents[idx]
                )

        merged = {}

        for item, _ in bm25_ranked:
            merged[item["id"]] = item

        for item in vector_results:
            merged[item["id"]] = item

        return list(merged.values())[:top_k]
