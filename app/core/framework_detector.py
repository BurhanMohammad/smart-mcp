from pathlib import Path


class FrameworkDetector:
    def detect(self, repo_path: str):
        repo = Path(repo_path)

        if (repo / "manage.py").exists():
            return {
                "language": "python",
                "framework": "django",
            }

        if (repo / "requirements.txt").exists():
            reqs = (repo / "requirements.txt").read_text()

            if "fastapi" in reqs.lower():
                return {
                    "language": "python",
                    "framework": "fastapi",
                }

            if "flask" in reqs.lower():
                return {
                    "language": "python",
                    "framework": "flask",
                }

        if (repo / "package.json").exists():
            package = (repo / "package.json").read_text()

            if "react" in package.lower():
                return {
                    "language": "typescript",
                    "framework": "react",
                }

        if (repo / "pubspec.yaml").exists():
            return {
                "language": "dart",
                "framework": "flutter",
            }

        return {
            "language": "unknown",
            "framework": "unknown",
        }