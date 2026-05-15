class Ranker:
    def rank(self, results):
        ranked = sorted(
            results,
            key=lambda x: x.get("score", 0),
            reverse=True,
        )

        return ranked