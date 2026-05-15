class TokenOptimizer:
    def optimize(self, content: str):
        optimized = []

        for line in content.splitlines():
            stripped = line.strip()

            if stripped.startswith("#"):
                continue

            if stripped == "":
                continue

            optimized.append(line)

        return "\n".join(optimized)