"""AGENTS.md Gate — enforce mandatory rules via pre_tool_call interception.

Rules enforced:
  1. Search routing: web_search / web_extract AND every MCP search/extract tool
     blocked until search-router or search-first skill is loaded
     (AGENTS.md "搜索路由（强制）").
     A skill pinned by skills.auto_load counts as loaded (it never produces a
     skill_view event) and is announced once via the normal [skill] marker.
  1b. Shell escape hatches: curl/wget/search-engine URLs inside terminal /
     execute_code are gated the same way.
  2. Codebase analysis: read_file on large-project paths warns to use codegraph
     MCP first (AGENTS.md "代码库分析（强制）").
"""

import json
import os
import re
import time
from pathlib import Path

# ── per-task state ──────────────────────────────────────────────────
# task_id -> {"loaded_skills": set, "loaded_mcp_tools": set,
#             "turn_skills": list, "turn_search": list, "last_reset": float}
_STATE: dict[str, dict] = {}

# State TTL: 2 hours; tasks older than this are evicted to bound memory.
_STATE_TTL = 7200


def _get_state(task_id: str = "", session_id: str = "") -> dict:
    key = task_id or session_id or os.environ.get("HERMES_SESSION_ID", "default")
    s = _STATE.get(key)
    now = time.time()
    if s is None or now - s.get("last_reset", 0) > _STATE_TTL:
        s = {"loaded_skills": set(), "loaded_mcp_tools": set(),
             "turn_skills": [], "turn_search": [], "last_reset": now}
        _STATE[key] = s
    return s


# ── helpers ─────────────────────────────────────────────────────────

def _is_large_project(path: str) -> bool:
    """Heuristic: >2 dir levels deep or >20 files = large project.

    Uses os.listdir (single dir scan) instead of rglob to avoid O(n) on
    huge trees; falls back to depth check only.
    """
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return False
        if p.is_file():
            p = p.parent
        depth = len(p.relative_to(p.anchor).parts) if p.anchor else len(p.parts)
        if depth > 2:
            return True
        # Cheap file count: one directory listing, no recursion.
        try:
            count = sum(1 for _ in p.iterdir() if _.is_file())
            return count > 20
        except (OSError, PermissionError):
            return False
    except Exception:
        return False


def _codegraph_enabled() -> bool:
    try:
        from hermes_cli.config import load_config
        cfg = load_config()
        mcp = cfg.get("mcp_servers", {})
        return bool(mcp.get("codegraph", {}).get("enabled", False))
    except Exception:
        return False


def _user_override() -> bool:
    """Allow explicit opt-out via config: plugins.entries.agents-md-gate.allow_override."""
    try:
        from hermes_cli.config import load_config
        cfg = load_config()
        entries = cfg.get("plugins", {}).get("entries", {})
        gate = entries.get("agents-md-gate", {})
        return bool(gate.get("allow_tool_override", False))
    except Exception:
        return False


# ── auto_load awareness ─────────────────────────────────────────────
# skills.auto_load pins a skill into every session's system prompt, so the
# agent never calls skill_view for it. Treat those names as loaded for the
# search-routing gate, and announce them through the normal [skill] marker
# on the first search of the session. Cached: load_config() is not cheap.
_AUTO_LOAD_CACHE: dict = {"names": set(), "ts": 0.0}
_AUTO_LOAD_TTL = 60.0


def _auto_load_search_skills() -> set:
    """Names from skills.auto_load that satisfy the search-routing gate."""
    now = time.time()
    if _AUTO_LOAD_CACHE["ts"] and now - _AUTO_LOAD_CACHE["ts"] < _AUTO_LOAD_TTL:
        return _AUTO_LOAD_CACHE["names"]
    names: set = set()
    try:
        from agent.skill_commands import resolve_auto_load_skills
        names = set(resolve_auto_load_skills() or [])
    except Exception:
        names = set()
    _AUTO_LOAD_CACHE["names"] = names
    _AUTO_LOAD_CACHE["ts"] = now
    return names


# ── search-tool detection ───────────────────────────────────────────
# Keyword match, not suffix match. The previous suffix list caught only 8 of
# the 24 real search/extract tools — `tavily_extract` ends in `_extract`, not
# `__extract`, so it and 15 others were never announced or gated.
_SEARCH_WORDS = ("search", "scrape", "extract", "fetch", "crawl", "map",
                 "research", "agent_run")
_NON_SEARCH = (
    "cronjob", "todo", "process_manage", "session_search", "computer_use",
    "list_prompts", "read_resource", "get_prompt", "credit_usage",
    "monitor_", "feedback",
    "score",  # anysearch telemetry: no search, matches only via provider name
)


def _is_search_tool(tool_name: str) -> bool:
    """True for any MCP tool that reaches the network to find or fetch content."""
    if not tool_name.startswith("mcp__"):
        return False
    low = tool_name.lower()
    if any(x in low for x in _NON_SEARCH):
        return False
    return any(w in low for w in _SEARCH_WORDS)


def _query_of(args: dict) -> str:
    """Best-effort human-readable label for what a tool was asked to do."""
    for key in ("query", "queries", "url", "urls", "domain", "domains",
                "objective", "prompt"):
        val = args.get(key)
        if val:
            return str(val)[:200]
    return ""


# ── shell escape-hatch detection ────────────────────────────────────
# `terminal` / `execute_code` can reach the network just as easily as
# web_search does, so keyword-matching tool names alone left the gate with
# a hole: `curl <url>` and `gh api` sailed straight through.
#
# We deliberately do NOT gate the whole tool — that would force a skill load
# before `ls`, `git status` or reading a file, which is pure noise. Instead we
# look at the COMMAND STRING, and only act when it actually fetches data.

_SHELL_TOOLS = ("terminal", "execute_code")

# Commands that never reach the network. Checked with a word-boundary match
# at the START of the command (after optional sudo/env prefixes), so
# `ls` passes but `curl -s https://…` does not.
_LOCAL_CMD = (
    "ls", "cat", "head", "tail", "grep", "rg", "sed", "awk", "find", "fd",
    "git", "echo", "wc", "stat", "du", "df", "ps", "pgrep", "cd", "pwd",
    "mkdir", "chmod", "chown", "cp", "mv", "rm", "ln", "touch", "which",
    "date", "diff", "less", "more", "sort", "uniq", "cut", "tr", "basename",
    "dirname", "realpath", "id", "whoami", "uname", "hostname", "free",
    "lsof", "tree", "jq", "python", "pip", "npm", "node", "uv",
)

# Hard blockers: these can ONLY be doing network retrieval.
_FETCH_CMDS = (
    "curl", "wget", "aria2c", "http", "httpie", "xh", "fetch",
    "lynx", "w3m", "links", "elinks",
)

# Search engines reachable as plain URLs.
_SEARCH_HOSTS = (
    "google.com", "bing.com", "duckduckgo.com", "baidu.com", "yandex.com",
    "search.brave.com", "ecosia.org", "startpage.com", "sogou.com",
    "so.com", "lite.duckduckgo.com", "googleapis.com/search",
)

_SHELL_QMARK = r"(?:^|[\s;|&(])({})\b"


def _shell_command(tool_name: str, args: dict) -> str:
    """Extract the shell command text from terminal/execute_code args.

    terminal takes `command`; execute_code runs Python where the network
    calls live inside the source string. Both are flattened to one blob and
    scanned — matching a curl inside a heredoc works the same way.
    """
    parts = []
    for key in ("command", "code", "script", "cmd"):
        val = args.get(key)
        if isinstance(val, str) and val:
            parts.append(val)
    return "\n".join(parts)


def _classify_shell(cmd: str) -> str:
    """Return 'fetch' | 'search' | '' for a shell command string."""
    if not cmd or not cmd.strip():
        return ""
    low = cmd.lower()

    # Strip common leading wrappers so `sudo curl` / `env X=1 curl` still
    # hits the local-command check below without a false "local".
    stripped = low.lstrip()
    for pfx in ("sudo ", "env ", "time ", "nohup ", "xargs ", "sh -c ", "bash -c "):
        while stripped.startswith(pfx):
            stripped = stripped[len(pfx):].lstrip()

    first = re.split(r"[\s;|&]", stripped, 1)[0]
    if first in _LOCAL_CMD:
        # Still let a search URL inside a `python -c` / `node -e` slip past:
        # those are legitimately local interpreters doing network work.
        if not any(h in low for h in _SEARCH_HOSTS):
            return ""

    for h in _SEARCH_HOSTS:
        if h in low:
            return "search"
    if re.search(_SHELL_QMARK.format("|".join(_FETCH_CMDS)), low):
        return "fetch"
    return ""


# ── pre_tool_call ───────────────────────────────────────────────────

def _pre_tool_call(tool_name: str, args: dict, task_id: str = "",
                   session_id: str = "", **kwargs):
    # P0-1 fail-open: a bug inside this gate must never take down every search.
    try:
        return _pre_tool_call_inner(tool_name, args, task_id, session_id, **kwargs)
    except Exception:
        return None


def _pre_tool_call_inner(tool_name: str, args: dict, task_id: str = "",
                         session_id: str = "", **kwargs):
    if _user_override():
        return None

    state = _get_state(task_id, session_id)
    # A real skill_view load. Rule 1b (shell escape hatches) keys off THIS and
    # nothing else, so curl/wget keep their original behaviour.
    skill_loaded = bool(state["loaded_skills"] & {"search-router", "search-first"})
    # skills.auto_load pins the skill into the session prompt without a
    # skill_view call, so loaded_skills stays empty for it. It satisfies Rule 1
    # (the native + MCP search tools) and must NOT be folded into skill_loaded,
    # or Rule 1b would silently stop blocking shell fetches.
    auto_satisfies = False
    if not skill_loaded:
        auto_satisfies = bool(_auto_load_search_skills() & {"search-router", "search-first"})

    # ── Rule 1: Search routing ──
    # Gate the MCP search/extract tools too, not just the native ones. The
    # mandatory parameter rules (e.g. exa's required `objective`) exist only
    # at the MCP layer, so gating only web_search/web_extract left them
    # unenforced.
    if tool_name in ("web_search", "web_extract") or _is_search_tool(tool_name):
        # An auto-loaded skill produces no skill_view event; announce it once,
        # on the first search of the session, exactly like a real load would.
        if auto_satisfies and not state.get("auto_load_announced"):
            state["auto_load_announced"] = True
            for name in sorted(_auto_load_search_skills() & {"search-router", "search-first"}):
                if name not in state["turn_skills"]:
                    state["turn_skills"].append(name)
        if not (skill_loaded or auto_satisfies):
            if tool_name == "web_extract":
                msg = (
                    "🚫 提取路由违规：你尚未加载搜索路由 skill。\n\n"
                    "AGENTS.md 强制要求：调用任何提取/抓取工具前必须先加载对应 skill。\n\n"
                    "请按以下步骤执行：\n"
                    "1. 调用 skill_view(name='search-router') 加载路由 skill\n"
                    "2. 由 skill 内的路由表选择引擎与参数\n"
                    "   ⚠️ batch_search / tavily_extract / exa__web_fetch_exa 的数组入参\n"
                    "      在本环境不可用，改用标量参数或单 URL 工具\n"
                    "3. 完成后在回复开头标注 [skill] 与 [搜索工具]（插件自动注入）\n\n"
                    "原生 web_extract 仅作最后兜底。"
                )
            else:
                msg = (
                    "🚫 搜索路由违规：你尚未加载搜索路由 skill。\n\n"
                    "AGENTS.md 强制要求：调用任何搜索工具前必须先加载对应 skill。\n\n"
                    "请按以下步骤执行：\n"
                    "1. 调用 skill_view(name='search-router') 加载路由 skill\n"
                    "2. 由 skill 内的路由表选择引擎与参数\n"
                    "   ⚠️ batch_search / tavily_extract / exa__web_fetch_exa 的数组入参\n"
                    "      在本环境不可用，改用标量参数或单 URL 工具\n"
                    "3. 完成后在回复开头标注 [skill] 与 [搜索工具]（插件自动注入）\n\n"
                    "原生 web_search 仅作最后兜底（所有 MCP 工具失败后）。"
                )
            return {"action": "block", "message": msg}

    # ── Rule 1b: shell escape hatches (hard tier) ──
    # `curl <search-engine>` / `wget` in a terminal command reaches the network
    # exactly like web_search does, so the same skill requirement applies.
    if tool_name in _SHELL_TOOLS and not skill_loaded:
        kind = _classify_shell(_shell_command(tool_name, args))
        if kind in ("fetch", "search"):
            return {
                "action": "block",
                "message": (
                    f"🚫 搜索路由违规（shell 出口）：`{tool_name}` 里的命令正在联网取数，"
                    "但你尚未加载搜索路由 skill。\n\n"
                    "AGENTS.md 强制要求：任何联网检索/抓取前必须先加载对应 skill，"
                    "shell 里的 curl/wget 也不例外。\n\n"
                    "请执行：\n"
                    "1. skill_view(name='search-router') 加载路由 skill\n"
                    "2. 优先改用 skill 内的 MCP 引擎工具（tavily_search / "
                    "firecrawl_scrape / anysearch__extract 等）\n"
                    "3. 若确实必须用 shell（如批量文件操作中的网络请求），"
                    "加载 skill 后再重试\n\n"
                    "本地命令（ls/grep/git/cat 等）不受此限制。"
                ),
            }

    # ── Rule 2: Codebase analysis ──
    if tool_name == "read_file":
        path = args.get("path", "")
        if _is_large_project(path) and _codegraph_enabled():
            if "codegraph_explore" not in state["loaded_mcp_tools"]:
                return {
                    "action": "block",
                    "message": (
                        "⚠️ 检测到大项目路径。AGENTS.md 要求：\n"
                        "处理大体量项目时，优先使用 codegraph MCP 工具定位，再用 read_file 精读。\n\n"
                        "请先调用 mcp__codegraph__codegraph_explore 定位，再读取具体文件。"
                    ),
                }

    return None


# ── post_tool_call ──────────────────────────────────────────────────

def _post_tool_call(tool_name: str, args: dict, result: str,
                    task_id: str = "", session_id: str = "", **kwargs):
    state = _get_state(task_id)

    if tool_name == "skill_view":
        name = args.get("name", "")
        if name:
            state["loaded_skills"].add(name)
            # Announce EVERY skill this turn, not just the search ones.
            if name not in state["turn_skills"]:
                state["turn_skills"].append(name)

    if tool_name.startswith("mcp__codegraph__"):
        state["loaded_mcp_tools"].add(tool_name.replace("mcp__codegraph__", ""))

    # ── Track every search/extract tool used this turn ──
    if tool_name in ("web_search", "web_extract") or _is_search_tool(tool_name):
        state.setdefault("turn_search", []).append(
            {"tool": tool_name, "query": _query_of(args)}
        )


# ── transform_llm_output: prepend [skill] / [搜索工具] markers ─────

def _transform_llm_output(response_text: str, task_id: str = "",
                          session_id: str = "", **kwargs) -> str:
    """Prepend AGENTS.md-mandated markers if missing."""
    if not response_text or not response_text.strip():
        return response_text
    
    # 群聊 / 频道不追加标记，直接返回（群聊回复短、干净）
    chat_type = kwargs.get("chat_type", "dm")
    if chat_type in {"group", "guild"}:
        return response_text
    
    state = _get_state(task_id, session_id)
    parts = []

    # Skills loaded THIS turn — drained after emitting, so each load is
    # announced exactly once instead of on every reply for the whole session.
    turn_skills = state.get("turn_skills") or []
    if turn_skills:
        parts.append("[skill] " + ", ".join(turn_skills))

    # Search/extract tools used THIS turn — one line, all of them (the old
    # single `last_search` slot kept only the most recent call).
    turn_search = state.get("turn_search") or []
    if turn_search:
        parts.append(
            "[搜索工具] "
            + ", ".join(
                f'{s["tool"]}: "{s["query"]}"' if s.get("query") else s["tool"]
                for s in turn_search
            )
        )

    state["turn_skills"] = []
    state["turn_search"] = []

    if not parts:
        return response_text

    prefix = "\n".join(parts) + "\n"
    if response_text.startswith(prefix):
        return response_text
    return prefix + response_text


# ── registration ────────────────────────────────────────────────────

def register(ctx):
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("post_tool_call", _post_tool_call)
    ctx.register_hook("transform_llm_output", _transform_llm_output)