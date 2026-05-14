import networkx as nx


class CallGraph:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_call(
        self,
        caller: str,
        callee: str,
    ):
        self.graph.add_edge(
            caller,
            callee,
            relation="calls",
        )

    def get_call_chain(self, symbol: str):
        if symbol not in self.graph:
            return []

        return list(nx.dfs_preorder_nodes(self.graph, symbol))