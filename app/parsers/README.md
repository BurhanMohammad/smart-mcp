# Smart MCP Token Optimizer

Smart MCP is a **local MCP retrieval engine** that dramatically reduces the tokens consumed by AI coding agents (Claude Code, Codex, Cursor, Continue, and any MCP-compatible AI).

It automatically indexes your repository and returns only the **minimum relevant code context** for any given task — so the AI never loads entire files or re-reads the whole codebase on every turn.

---

## The Problem

Large repositories create massive token waste.

A typical Django project may contain:

- `views.py` with 9,000+ lines
- `serializers.py` with 2,000+ lines
- 100+ migration files
- Static vendor assets (jQuery, select2, Bootstrap CSS)
- Repeated boilerplate across modules

Without Smart-MCP, an AI agent dealing with a bug fix will often load 40K–120K tokens of context — most of it irrelevant. Over a multi-step session this balloons to 500K+ tokens.

---

## The Solution

Smart MCP sits between your repository and the AI as a retrieval layer:

```
Repository → Full Context → LLM            ← WITHOUT Smart-MCP (500K+ tokens)

Repository
→ AST Parsing
→ Symbol Extraction
→ Chunking (real source code per symbol)
→ BM25 Keyword Index
→ FAISS Vector Index
→ Call Graph (Python AST + regex)
→ Route Mapping
→ Reciprocal Rank Fusion
→ Token-Budget Filtering
→ Minimal Relevant Context → LLM           ← WITH Smart-MCP (3K–50K tokens)
```

---

## Token Reduction Numbers

| Workflow | Without Smart-MCP | With Smart-MCP | Reduction |
|---|---|---|---|
| Bug fix | 40K–120K tokens | 3K–12K tokens | ~90% |
| Feature addition | 80K tokens | 8K–15K tokens | ~85% |
| Multi-step session | 500K+ tokens | 30K–60K tokens | ~88% |
| First repo orientation | 200K+ tokens | 400–600 tokens | ~99.7% |

**Estimated reduction: 70%–92% on large repositories.**

A real analysis of a Django API repository showed Smart-MCP reducing a 500K–900K token read (if all files were loaded at once) down to **10K–50K tokens per query** — a 10–50× reduction.

---

## Key Features

### Real Code in Every Chunk
Every indexed symbol carries actual source code lines, not just a name label. This makes both keyword search and semantic search dramatically more accurate.

### Hybrid Retrieval with RRF
Combines BM25 keyword search with FAISS dense-vector search, fused using **Reciprocal Rank Fusion** — proven to outperform simple score averaging.

### Token Budget Control
`search_with_budget(query, max_tokens=3000)` returns exactly as much context as fits in your budget. The AI never accidentally blows its context window.

### Call Graph Traversal
Built from Python AST call extraction + regex for TypeScript/Dart/Go. Enables `get_related`, `get_call_chain`, `explain_symbol`, and `find_dead_code`.

### Route-to-View Mapping
Maps URL routes to handler functions for Django, FastAPI, Flask, Express.js, and Next.js.

### Serializer-Model Linking
Automatically maps Django REST Framework serializers to their backing models.

### Persistent FAISS Index
FAISS vector index is saved to disk and reloaded on server restart — no re-embedding on every start.

### Incremental Indexing
File hashes are persisted so only changed files are re-indexed. Fast startup on large repos.

### Multi-Repository Support
Index multiple repositories and search across all of them simultaneously.

### 15+ Languages Supported
Python, TypeScript, JavaScript, Dart/Flutter, Go, Java, Kotlin, Rust, Ruby, PHP, C#, Swift, C/C++.

### Configurable
Drop a `smart-mcp.config.json` in your repo root to customize embedding model, excluded dirs, token budget, and more.

---

## Supported Frameworks

**Backend:** Django, FastAPI, Flask, Express, NestJS, Fastify, Spring, Rails, Laravel, Symfony, Gin, Axum, Actix

**Frontend:** React, Next.js, Vue, Nuxt, Svelte, TypeScript

**Mobile:** Flutter/Dart

**Other:** Go, Rust, Java/Kotlin, Ruby, PHP, C#/.NET, Swift

---

## Installation

### 1. Create a virtual environment

Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

macOS / Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> **Optional:** For exact token counting instead of the fast approximation:
> ```bash
> pip install tiktoken
> ```

---

## Setup — Choose One Path

### Option A: Global Setup (recommended — works across all projects)

Run **once** on your machine. Smart-MCP will automatically index whatever project you open in Claude Code, Cursor, or Codex — no per-project configuration needed.

```bash
python C:\Work\smart-mcp\setup_global.py
```

What this does:
- Registers Smart-MCP in all AI clients found on your machine (Claude Code, Cursor, Codex, Claude Desktop, Windsurf, Continue)
- Writes `~/.claude/CLAUDE.md` — global instructions so Claude automatically uses Smart-MCP tools when you type naturally
- Warns about and optionally clears any hardcoded `REPO_PATH` in `.env`

After this, just open any project in Claude Code and type naturally:

```
the login is not working
```

Claude reads the CLAUDE.md instructions and calls Smart-MCP tools automatically. You never need to mention tool names.

To preview without writing files:
```bash
python setup_global.py --dry-run
```

---

### Option B: Per-Project Setup (for pre-building the index)

Use this if you want to pre-build the index for a specific project so the first query is instant.

```bash
# From inside the project:
python C:\Work\smart-mcp\setup_project.py

# Or pass path explicitly:
python C:\Work\smart-mcp\setup_project.py C:\Work\MyProject

# Skip index pre-build:
python C:\Work\smart-mcp\setup_project.py --no-index
```

What this does:
- Writes `<project>/.claude/mcp.json` — wires Smart-MCP for this project
- Writes `<project>/CLAUDE.md` — auto-dispatch instructions for Claude
- Pre-builds the index now (so first query is instant)

---

### How Multi-Project Works

After `setup_global.py`, Smart-MCP auto-detects the project using this priority:

```
1. CLI argument        python -m app.mcp.server <path>
2. AI client env var   CLAUDE_PROJECT_DIR / VSCODE_WORKSPACE_FOLDER / PROJECT_ROOT / …
3. REPO_PATH in .env   (commented out by default — leave it commented for multi-project use)
4. Auto-detect cwd     ← default after global setup
```

So when you open `C:\Work\ProjectA` in Claude Code, Smart-MCP indexes `ProjectA`.
When you open `C:\Work\ProjectB`, it indexes `ProjectB`. No config changes needed.

---

### Manual Server Start (advanced)

```bash
# Auto-detect project from current directory:
python -m app.mcp.server

# Explicit path:
python -m app.mcp.server C:\Work\MyProject

# Force full re-index (ignore cache):
python -m app.mcp.server C:\Work\MyProject --force
```

---

## Configuration

Drop a `smart-mcp.config.json` in your **repository root** to customize behaviour:

```json
{
  "embedding_model":      "BAAI/bge-small-en-v1.5",
  "max_file_kb":          500,
  "top_k_default":        8,
  "token_budget_default": 3000,
  "excluded_dirs":        ["custom_vendor", "auto_generated"],
  "index_on_startup":     true,
  "cache_subdir":         ".smart-mcp-cache",
  "graph_depth_default":  1
}
```

**Available models** (trade-off: speed vs quality):

| Model | Size | Speed | Quality |
|---|---|---|---|
| `BAAI/bge-small-en-v1.5` | 33M | ⚡ Fast | Good (default) |
| `BAAI/bge-base-en-v1.5` | 109M | Moderate | Better |
| `BAAI/bge-large-en-v1.5` | 335M | Slow | Best |

**Environment variable overrides:**

| Env Var | Config Key | Example |
|---|---|---|
| `SMART_MCP_MODEL` | `embedding_model` | `BAAI/bge-base-en-v1.5` |
| `SMART_MCP_MAX_FILE_KB` | `max_file_kb` | `200` |
| `SMART_MCP_TOP_K` | `top_k_default` | `10` |
| `SMART_MCP_TOKEN_BUDGET` | `token_budget_default` | `4000` |

---

## MCP Tools Reference (15 tools)

### SEARCH

---

#### `search_context` *(primary tool)*

Hybrid BM25 + FAISS semantic search with RRF score fusion.

```
search_context(
  query:       str,           # natural language or symbol name
  top_k:       int = 8,       # max results
  file_filter: str = "",      # narrow to files containing this string
  symbol_type: str = ""       # function | class | method | route | …
)
```

Returns each result with: `symbol`, `type`, `file`, `start_line`, `end_line`, `class_name`, `decorators`, `docstring`, `code`, `score`.

---

#### `search_with_budget`

Token-budget-aware search — returns results that fit inside `max_tokens`.

```
search_with_budget(
  query:      str,
  max_tokens: int = 3000,   # token budget
  file_filter: str = "",
  symbol_type: str = ""
)
```

Returns: `used_tokens`, `budget_pct`, and trimmed results.

---

#### `search_signatures`

Returns only function signatures — no body code. ~10–30 tokens per result.

```
search_signatures(
  query:       str,
  top_k:       int = 20,
  file_filter: str = ""
)
```

---

#### `search_by_file`

List or search symbols scoped to a specific file.

```
search_by_file(
  file_path: str,      # partial path: "views.py" or "auth/serializers"
  query:     str = "", # optional re-rank query
  limit:     int = 30
)
```

---

### SYMBOL LOOKUP

---

#### `get_symbol`

Exact-match lookup. Returns full source code.

```
get_symbol(
  name: str,
  file: str = ""   # optional disambiguator
)
```

---

#### `find_usages`

Find where a symbol is referenced (called/imported/used) — not defined.

```
find_usages(
  symbol_name: str,
  top_k:       int = 8
)
```

---

#### `explain_symbol`

Full context in one call: definition + callers + callees.

```
explain_symbol(
  name: str,
  file: str = ""
)
```

Saves 60–70% of tokens vs chaining `get_symbol` + `find_usages` + `get_related`.

---

### GRAPH TRAVERSAL

---

#### `get_related`

BFS graph expansion: symbols within N hops (callers + callees + inheritance).

```
get_related(
  symbol_name:  str,
  depth:        int  = 1,
  include_code: bool = True   # False = signatures only
)
```

---

#### `get_call_chain`

Follow the call chain from a symbol N levels deep.

```
get_call_chain(
  symbol_name: str,
  depth:       int = 3,
  direction:   str = "down"   # "down" = dependencies, "up" = dependants
)
```

---

### NAVIGATION

---

#### `list_symbols`

Browse all indexed symbols without a search query.

```
list_symbols(
  file_pattern: str = "",
  symbol_type:  str = "",
  limit:        int = 50
)
```

---

#### `list_routes`

All URL routes mapped to handler functions.

```
list_routes(
  method:      str = "",   # GET | POST | PUT | DELETE | …
  path_filter: str = ""
)
```

---

#### `list_serializers`

Django REST Framework serializer → model mapping.

```
list_serializers(
  model_filter: str = ""
)
```

---

### ANALYSIS

---

#### `get_repo_summary`

Full codebase overview in ~300–600 tokens.

```
get_repo_summary()
```

Returns: framework, languages, file counts, top files, models, routes summary, hot symbols (most-called), dead code estimate, index health.

**Use this first when starting work on an unfamiliar repository.**

---

#### `find_dead_code`

Symbols defined but never called anywhere in the indexed codebase.

```
find_dead_code(
  limit: int = 20
)
```

---

#### `get_index_stats`

Index health: chunks, files, type distribution, graph edges, model, timestamps.

```
get_index_stats()
```

---

### MULTI-REPO

---

#### `list_repos`

List all indexed repositories (single-repo or multi-repo mode).

```
list_repos()
```

---

#### `search_all_repos`

Search across ALL indexed repos simultaneously. Results merged with RRF.

```
search_all_repos(
  query:  str,
  top_k:  int = 8
)
```

---

## How to Use — Just Type Naturally

After running `setup_global.py` or `setup_project.py`, a `CLAUDE.md` file is written to your project (or globally to `~/.claude/CLAUDE.md`). Claude reads this automatically and knows to use Smart-MCP tools — **you never need to mention tool names**.

Just describe what you want in plain language.

---

### Fixing bugs

```
the authentication is not working
```
```
login keeps returning 403
```
```
JWT token validation is broken
```
```
there's a bug in the order creation flow
```

→ Claude automatically calls `search_with_budget("authentication issue", 4000)`, finds the relevant functions, and fixes the bug.

---

### Understanding code

```
how does the payment flow work
```
```
explain the user registration process
```
```
what does the validate_token function do
```

→ Claude calls `explain_symbol("validate_token")` or `get_call_chain("process_payment")` automatically.

---

### Adding features

```
add email notifications when an order is shipped
```
```
implement a new endpoint for user profile update
```
```
add rate limiting to the login endpoint
```

→ Claude calls `get_repo_summary()`, then `search_with_budget("order notifications")`, then `list_routes()` to understand existing patterns.

---

### Exploring the codebase

```
give me an overview of this project
```
```
what API endpoints do we have
```
```
what models does this Django app have
```
```
how is the Order model serialized
```

→ Claude calls `get_repo_summary()`, `list_routes()`, `list_serializers(model_filter="Order")` etc. automatically.

---

### Refactoring

```
I need to rename validate_user to authenticate_user — what will break?
```
```
clean up the auth module
```

→ Claude calls `get_related("validate_user", depth=2)` then `find_usages("validate_user")` to map the full impact.

---

### Tracing execution

```
trace what happens when a user logs in
```
```
follow the payment processing flow from the API endpoint
```

→ Claude calls `get_call_chain("login_view", depth=3, direction="down")`.

---

### Finding dead code

```
are there any unused functions we should clean up
```

→ Claude calls `find_dead_code(limit=30)`.

---

## Example Prompts Showing Token Savings

| User types | What Claude does | Token cost | Without Smart-MCP |
|---|---|---|---|
| `"give me an overview"` | `get_repo_summary()` | ~400 tok | 200K+ tok (read all files) |
| `"login is broken"` | `search_with_budget("login", 4000)` | ~2K–4K tok | 40K–120K tok |
| `"what calls validate_token"` | `find_usages("validate_token")` | ~500 tok | 20K+ tok |
| `"explain create_order"` | `explain_symbol("create_order")` | ~1K–2K tok | 15K–40K tok |
| `"what auth functions exist"` | `search_signatures("auth", top_k=20)` | ~200 tok | 5K–20K tok |
| `"what endpoints do we have"` | `list_routes()` | ~300 tok | 10K tok (read all urls.py) |
| `"how is User serialized"` | `list_serializers("User")` | ~100 tok | 5K tok |

---

## Architecture

```
smart-mcp/
├── app/
│   ├── chunking/
│   │   └── ast_chunker.py        # Build rich chunks with real source code
│   ├── core/
│   │   ├── code_extractor.py     # Read/cache actual source lines
│   │   ├── file_scanner.py       # Scan files (15+ languages, gitignore)
│   │   ├── framework_detector.py # Detect 20+ frameworks
│   │   ├── hybrid_retriever.py   # BM25 + FAISS + RRF + graph
│   │   ├── graph_builder.py      # Call graph from AST + regex
│   │   ├── incremental_indexer.py# Persistent file-hash cache
│   │   ├── route_mapper.py       # URL → handler mapping
│   │   ├── serializer_linker.py  # Django serializer → model
│   │   ├── multi_repo_manager.py # Multi-repo index management
│   │   ├── repo_summarizer.py    # Codebase overview generator
│   │   └── token_counter.py      # Token counting + budget filtering
│   ├── mcp/
│   │   ├── server.py             # FastMCP server (17 tools)
│   │   └── tools.py              # Tool implementations + state
│   ├── parsers/
│   │   ├── python_parser.py      # AST: decorators, calls, docstrings
│   │   ├── typescript_parser.py  # Regex: funcs, classes, interfaces, routes
│   │   ├── flutter_parser.py     # Regex: widgets, mixins, extensions
│   │   └── go_parser.py          # Regex: funcs, structs, interfaces
│   ├── templates/
│   │   └── CLAUDE.md             # ← Auto-dispatch instructions for Claude
│   ├── config.py                 # Config loader (file + env + defaults)
│   └── main.py                   # Indexing orchestrator
├── setup_global.py               # ← One-time machine-wide setup
├── setup_project.py              # ← Per-project setup + index pre-build
├── requirements.txt
├── .env                          # REPO_PATH (leave commented for multi-project)
└── README.md
```

---

## Core Components

| Component | Purpose | Token Impact |
|---|---|---|
| `HybridRetriever` | BM25 + FAISS + RRF fusion | Retrieves 8 chunks vs loading whole files |
| `GraphBuilder` | AST call graph | Powers `get_related`, `explain_symbol`, dead code |
| `TokenCounter` | Budget-aware filtering | `search_with_budget` never overruns context |
| `ASTChunker` | Real code in chunks | Embedding quality ↑ → fewer irrelevant results |
| `RouteMapper` | URL → handler | Find views without reading urls.py |
| `SerializerLinker` | Serializer → model | Direct model↔serializer lookup |
| `RepoSummarizer` | Overview in 400 tokens | Orient AI in seconds, not thousands of tokens |
| `MultiRepoManager` | Cross-repo search | Monorepo and microservice support |
| `IncrementalIndexer` | Persistent hash cache | Fast re-index (only changed files) |

---

## Future Improvements

| Item | Status |
|---|---|
| Deeper AST relationships (decorators, base classes, return types, calls) | ✅ Done |
| Route-to-view mapping (Django, FastAPI, Flask, Express, Next.js) | ✅ Done |
| Persistent vector database (FAISS saved to disk) | ✅ Done |
| Better reranking (Reciprocal Rank Fusion) | ✅ Done |
| Advanced semantic compression (real code in chunks) | ✅ Done |
| Multi-language support (Go, Java, Kotlin, Rust, Ruby, PHP, C#, Swift) | ✅ Done |
| Incremental indexing with persistent hash cache | ✅ Done |
| Progress reporting during indexing (tqdm) | ✅ Done |
| Advanced graph traversal (`get_related`, `get_call_chain`) | ✅ Done |
| Serializer-model linking (Django REST Framework) | ✅ Done |
| Multi-repository memory and cross-repo search | ✅ Done |
| Token-budget-aware retrieval (`search_with_budget`) | ✅ Done |
| Repository summary tool (`get_repo_summary`) | ✅ Done |
| Dead code detection (`find_dead_code`) | ✅ Done |
| Signatures-only mode (`search_signatures`) | ✅ Done |
| File-based configuration (`smart-mcp.config.json`) | ✅ Done |
| Repository benchmark suite | 🔲 Planned |
| LSP-based exact Go / Java / Rust symbol extraction | 🔲 Planned |
| Semantic deduplication across a session | 🔲 Planned |
| Auto-generated CLAUDE.md / AGENTS.md from index | 🔲 Planned |

---

## Why Local-First?

Everything runs on your machine. No repository data is sent to external servers.

This is important for:
- Enterprise and proprietary codebases
- GDPR / data-residency requirements
- Air-gapped development environments
- Codebases that cannot leave the local network
