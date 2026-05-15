import networkx as nx


class ImportGraph:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_import(
        self,
        source_file: str,
        imported_module: str,
    ):
        self.graph.add_edge(
            source_file,
            imported_module,
            relation="import",
        )

    def get_dependencies(self, file_path: str):
        if file_path not in self.graph:
            return []

        return list(self.graph.neighbors(file_path))