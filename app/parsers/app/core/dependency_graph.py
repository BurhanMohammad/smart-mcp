import networkx as nx


class DependencyGraph:
    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def add_relation(
        self,
        source: str,
        target: str,
        relation_type: str,
    ):
        self.graph.add_edge(
            source,
            target,
            relation=relation_type,
        )

    def related_nodes(self, node: str):
        if node not in self.graph:
            return []

        return list(self.graph.neighbors(node))