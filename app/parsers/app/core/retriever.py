from rank_bm25 import BM25Okapi


class SemanticRetriever:
    def __init__(self, documents):
        self.documents = documents

        tokenized = [
            doc["text"].split()
            for doc in documents
        ]

        self.bm25 = BM25Okapi(tokenized)

    def search(self, query: str, top_k: int = 10):
        scores = self.bm25.get_scores(query.split())

        ranked = sorted(
            zip(self.documents, scores),
            key=lambda x: x[1],
            reverse=True,
        )

        return ranked[:top_k]