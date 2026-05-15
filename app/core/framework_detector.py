
from __future__ import annotations

import json
from pathlib import Path


class FrameworkDetector:
    """
    Detect the primary language and framework of a repository.

    Detection order (first match wins):
      1. Python frameworks  — manage.py, requirements.txt / pyproject.toml
      2. Node.js frameworks — package.json
      3. Dart / Flutter     — pubspec.yaml
      4. Go                 — go.mod
      5. Rust               — Cargo.toml
      6. Java / Kotlin      — pom.xml / build.gradle
      7. Ruby               — Gemfile
      8. PHP                — composer.json
      9. C# / .NET          — *.csproj / *.sln

    Returns a dict: {"language": "...", "framework": "...", "extra": [...]}
    """

    def detect(self, repo_path: str) -> dict:
        repo = Path(repo_path)

        # ── Python ──────────────────────────────────────────────────── #
        if (repo / "manage.py").exists():
            return self._result("python", "django")

        if (repo / "requirements.txt").exists():
            reqs = (repo / "requirements.txt").read_text(errors="ignore").lower()
            if "fastapi" in reqs:
                return self._result("python", "fastapi")
            if "flask" in reqs:
                return self._result("python", "flask")
            if "django" in reqs:
                return self._result("python", "django")
            return self._result("python", "python")

        if (repo / "pyproject.toml").exists():
            content = (repo / "pyproject.toml").read_text(errors="ignore").lower()
            for fw in ("fastapi", "flask", "django", "litestar", "tornado"):
                if fw in content:
                    return self._result("python", fw)
            return self._result("python", "python")

        # ── Node.js / JavaScript / TypeScript ───────────────────────── #
        if (repo / "package.json").exists():
            try:
                pkg = json.loads((repo / "package.json").read_text(errors="ignore"))
            except Exception:
                pkg = {}
            deps = {
                **pkg.get("dependencies", {}),
                **pkg.get("devDependencies", {}),
            }
            dep_lower = {k.lower(): v for k, v in deps.items()}

            if "next" in dep_lower:
                return self._result("typescript", "nextjs", ["react"])
            if "nuxt" in dep_lower:
                return self._result("typescript", "nuxtjs", ["vue"])
            if "@nestjs/core" in dep_lower:
                return self._result("typescript", "nestjs")
            if "express" in dep_lower:
                lang = "typescript" if (repo / "tsconfig.json").exists() else "javascript"
                return self._result(lang, "express")
            if "react" in dep_lower:
                lang = "typescript" if (repo / "tsconfig.json").exists() else "javascript"
                return self._result(lang, "react")
            if "vue" in dep_lower:
                return self._result("typescript", "vue")
            if "svelte" in dep_lower:
                return self._result("typescript", "svelte")
            if "fastify" in dep_lower:
                return self._result("typescript", "fastify")
            lang = "typescript" if (repo / "tsconfig.json").exists() else "javascript"
            return self._result(lang, "nodejs")

        # ── Dart / Flutter ──────────────────────────────────────────── #
        if (repo / "pubspec.yaml").exists():
            content = (repo / "pubspec.yaml").read_text(errors="ignore").lower()
            if "flutter" in content:
                return self._result("dart", "flutter")
            return self._result("dart", "dart")

        # ── Go ──────────────────────────────────────────────────────── #
        if (repo / "go.mod").exists():
            content = (repo / "go.mod").read_text(errors="ignore").lower()
            for fw in ("gin-gonic/gin", "labstack/echo", "gofiber/fiber",
                       "go-chi/chi", "gorilla/mux"):
                if fw in content:
                    framework = fw.split("/")[-1]
                    return self._result("go", framework)
            return self._result("go", "go")

        # ── Rust ────────────────────────────────────────────────────── #
        if (repo / "Cargo.toml").exists():
            content = (repo / "Cargo.toml").read_text(errors="ignore").lower()
            for fw in ("actix-web", "axum", "rocket", "warp"):
                if fw in content:
                    return self._result("rust", fw)
            return self._result("rust", "rust")

        # ── Java / Kotlin ────────────────────────────────────────────── #
        if (repo / "pom.xml").exists():
            content = (repo / "pom.xml").read_text(errors="ignore").lower()
            if "spring" in content:
                return self._result("java", "spring")
            return self._result("java", "maven")

        if (repo / "build.gradle").exists() or (repo / "build.gradle.kts").exists():
            build_file = (
                repo / "build.gradle.kts"
                if (repo / "build.gradle.kts").exists()
                else repo / "build.gradle"
            )
            content = build_file.read_text(errors="ignore").lower()
            lang = "kotlin" if "kotlin" in content else "java"
            if "spring" in content:
                return self._result(lang, "spring")
            return self._result(lang, "gradle")

        # ── Ruby ────────────────────────────────────────────────────── #
        if (repo / "Gemfile").exists():
            content = (repo / "Gemfile").read_text(errors="ignore").lower()
            if "rails" in content:
                return self._result("ruby", "rails")
            if "sinatra" in content:
                return self._result("ruby", "sinatra")
            return self._result("ruby", "ruby")

        # ── PHP ─────────────────────────────────────────────────────── #
        if (repo / "composer.json").exists():
            try:
                comp = json.loads((repo / "composer.json").read_text(errors="ignore"))
            except Exception:
                comp = {}
            require = {**comp.get("require", {}), **comp.get("require-dev", {})}
            require_lower = {k.lower(): v for k, v in require.items()}
            if "laravel/framework" in require_lower:
                return self._result("php", "laravel")
            if "symfony/symfony" in require_lower or any("symfony/" in k for k in require_lower):
                return self._result("php", "symfony")
            return self._result("php", "php")

        # ── C# / .NET ───────────────────────────────────────────────── #
        csproj = list(repo.glob("*.csproj")) or list(repo.rglob("*.csproj"))
        if csproj:
            return self._result("csharp", "dotnet")

        if list(repo.glob("*.sln")):
            return self._result("csharp", "dotnet")

        return self._result("unknown", "unknown")

    @staticmethod
    def _result(language: str, framework: str, extra: list | None = None) -> dict:
        return {
            "language":  language,
            "framework": framework,
            "extra":     extra or [],
        }
