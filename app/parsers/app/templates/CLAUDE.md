# Smart-MCP: Automatic Code Retrieval is Active

This project is connected to Smart-MCP, a local retrieval engine that indexes the entire codebase. Smart-MCP tools are available and **must be used instead of reading files directly**.

---

## Core Rules — Always Follow

1. **Never use the `Read` tool to load source files.** Smart-MCP retrieves the exact code needed.
2. **Never guess at code structure.** Always retrieve before answering.
3. **Start every new conversation** by calling `get_repo_summary()` silently to orient yourself.
4. **Use `search_with_budget`** as the default search tool — it keeps token usage under control.
5. **Do not tell the user you are calling tools.** Just call them and use the results naturally.

---

## Natural Language → Tool Mapping

The user will speak naturally. You translate their intent into the right tool call automatically.

### The user describes a bug or error

> "authentication is not working"
> "the login keeps failing"
> "JWT token validation is broken"
> "I'm getting a 403 on the payment endpoint"
> "there's a bug in the order creation flow"

```
→ search_with_budget(query="<their exact phrase>", max_tokens=4000)
→ If the results point to a specific function: explain_symbol("<function_name>")
→ Fix using only the retrieved code — never read full files
```

---

### The user wants to understand code

> "how does the authentication work"
> "explain the payment flow"
> "what does UserSerializer do"
> "how is the order created"

```
→ explain_symbol("<key symbol from their phrase>")
   OR search_with_budget(query="<their phrase>", max_tokens=3000)
→ If they ask about a class/function by name: get_symbol("<name>")
```

---

### The user wants to add a feature

> "I want to add email notifications"
> "add a new endpoint for user profile update"
> "implement password reset"
> "add pagination to the orders list"

```
→ get_repo_summary()  (understand structure first)
→ search_with_budget(query="<feature area>", max_tokens=4000)
→ list_routes()  (to understand existing endpoint patterns)
→ Build the feature using retrieved patterns as reference
```

---

### The user asks where something is

> "where is the login view"
> "find the JWT middleware"
> "show me the User model"
> "where is the payment processing code"

```
→ get_symbol("<symbol name>")
   OR search_context(query="<their phrase>", top_k=5)
```

---

### The user asks what calls something / impact analysis

> "what uses the validate_token function"
> "what will break if I change UserSerializer"
> "what depends on the payment service"

```
→ find_usages("<symbol_name>")
→ get_related("<symbol_name>", depth=2)
```

---

### The user asks about API routes or endpoints

> "what endpoints do we have"
> "show me all the POST routes"
> "which view handles /api/orders/"
> "list all the API endpoints"

```
→ list_routes()
→ list_routes(method="POST")  (if specific method mentioned)
→ list_routes(path_filter="orders")  (if specific path mentioned)
```

---

### The user asks about models or serializers (Django)

> "what models do we have"
> "how is the Order model serialized"
> "what fields does UserSerializer return"
> "show me the Product model"

```
→ search_context(query="<model name>", symbol_type="class")
→ list_serializers(model_filter="<model name>")
→ get_symbol("<ModelName>")
```

---

### The user asks about the codebase structure

> "give me an overview of this project"
> "what is this codebase"
> "what framework is this"
> "how is this repo structured"
> "what are the main components"

```
→ get_repo_summary()
```

---

### The user wants to refactor or rename

> "I need to rename validate_user to authenticate_user"
> "refactor the payment module"
> "clean up the auth code"

```
→ get_related("<symbol>", depth=2, include_code=False)  (signatures only — see scope)
→ find_usages("<symbol>")  (find all call sites)
→ Then make the targeted changes
```

---

### The user wants to trace execution / data flow

> "trace what happens when a user logs in"
> "follow the order creation flow"
> "what does process_payment call"

```
→ get_call_chain("<entry_function>", depth=3, direction="down")
→ explain_symbol("<entry_function>")
```

---

### The user is in a tight context window

> "I don't have many tokens left"
> "keep it short"
> (you notice context is getting long)

```
→ search_signatures(query="<topic>", top_k=15)   # signatures only ~15 tokens each
→ search_with_budget(query="<topic>", max_tokens=1500)
```

---

## Standard Workflow Templates

### Bug Fix Workflow

```
1. search_with_budget(query="<bug description>", max_tokens=4000)
2. Read the returned code — identify the issue
3. If you need the caller context: get_related("<function>", depth=1)
4. Fix the bug in the specific file/lines returned
5. Do NOT load any other files
```

### New Feature Workflow

```
1. get_repo_summary()                          → understand structure
2. search_with_budget(query="<feature>", max_tokens=4000)  → find similar patterns
3. list_routes()                               → check existing endpoints
4. list_serializers()                          → check existing serializers (Django)
5. Implement following existing patterns
```

### Code Review / Understanding Workflow

```
1. get_repo_summary()                          → orientation
2. search_signatures(query="<area>", top_k=20) → scan what exists cheaply
3. explain_symbol("<key function>")            → deep dive where needed
4. get_call_chain("<entry>", depth=2)          → trace flow if needed
```

---

## Token Efficiency Rules

- **Prefer `search_with_budget`** over `search_context` — it prevents accidental overruns.
- **Use `search_signatures` first** when exploring — ~20 tokens per result vs ~400.
- **Use `explain_symbol`** instead of chaining 3 separate tool calls.
- **Never call `search_all_repos`** unless the user explicitly asks to search all projects.
- **`get_repo_summary` costs ~400 tokens** — call it once at session start, not repeatedly.

---

## What Smart-MCP Cannot Do

- It cannot access files outside the indexed repository.
- It does not index `migrations/`, `static/`, `node_modules/`, `.git/`, or vendor directories.
- The index is built when the MCP server starts. If new files were just added, the index may not include them yet (run `python -m app.mcp.server --force` to re-index).
- For binary files, images, or non-source files, use normal file tools.
