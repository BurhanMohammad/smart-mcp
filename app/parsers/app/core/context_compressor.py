class ContextCompressor:
    def compress(
        self,
        content: str,
        max_lines: int = 120,
    ):
        lines = content.splitlines()

        important = []

        for line in lines:
            stripped = line.strip()

            if not stripped:
                continue

            if stripped.startswith("#"):
                continue

            important.append(line)

        return "\n".join(important[:max_lines])