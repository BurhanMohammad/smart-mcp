
RETRIEVER = None


def register_retriever(retriever):
    global RETRIEVER
    RETRIEVER = retriever


async def semantic_lookup(query: str):
    if RETRIEVER is None:
        return {
            "error": "Index not built"
        }

    return RETRIEVER.search(query)
