import networkx as nx


class ASTGraphEngine:
    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def add_symbol(self, file, symbol):
        self.graph.add_node(
            symbol,
            file=file
        )

    def add_dependency(self, source, target):
        self.graph.add_edge(
            source,
            target,
            relation="dependency"
        )

    def related(self, symbol):
        if symbol not in self.graph:
            return []

        return list(
            self.graph.neighbors(symbol)
        )
