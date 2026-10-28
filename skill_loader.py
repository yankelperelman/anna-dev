"""
skill_loader.py — skill auto-loader for Anna.

Every *.py file in the skills folder (except names starting with "_") is loaded
as a skill. A skill module may define:

  FUNCTION_DECLARATIONS           list of Gemini function declarations
  INSTRUCTION_ADDON               text appended to the system instruction
  async/sync execute(name, args)  runs a tool call, returns a string
  init(db_path, logger)           optional, called at server startup
  DYNAMIC_DECLARATIONS_PROVIDER   optional callable returning more declarations
                                  (queried again after init(), when they are known)
  shutdown()                      optional, called when the server stops
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

_log = logging.getLogger("skills")


async def _maybe_await(fn, *args) -> Any:
    result = fn(*args)
    if asyncio.iscoroutine(result):
        return await result
    return result


class SkillRegistry:
    def __init__(self, skills_dir: str, logger: logging.Logger | None = None):
        self._log = logger or _log
        self._skills: list[Any] = []
        self._declarations: list[dict] = []
        self._instructions: list[str] = []
        self._tool_map: dict[str, Any] = {}
        self._discover(skills_dir)

    def _discover(self, skills_dir: str) -> None:
        root = Path(skills_dir)
        if not root.is_dir():
            self._log.warning("Skills folder not found: %s", skills_dir)
            return
        for path in sorted(root.glob("*.py")):
            if path.name.startswith("_"):
                continue
            self._load_one(path)

    def _register(self, mod: Any, decls: list[dict], source: str) -> int:
        added = 0
        for d in decls:
            name = d.get("name")
            if not name:
                continue
            if name in self._tool_map:
                if self._tool_map[name] is mod:
                    continue
                self._log.warning("Tool %s is already declared, overwriting (%s)", name, source)
                self._declarations = [x for x in self._declarations if x.get("name") != name]
            self._declarations.append(d)
            self._tool_map[name] = mod
            added += 1
        return added

    def _load_one(self, path: Path) -> None:
        module_name = f"anna_skill_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                self._log.warning("Could not create a module spec for %s", path.name)
                return
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
        except Exception:
            self._log.exception("Skill %s failed to load", path.name)
            return

        decls = list(getattr(mod, "FUNCTION_DECLARATIONS", []) or [])

        dynamic_provider = getattr(mod, "DYNAMIC_DECLARATIONS_PROVIDER", None)
        if callable(dynamic_provider):
            try:
                decls.extend(dynamic_provider())
            except Exception:
                self._log.exception("DYNAMIC_DECLARATIONS_PROVIDER failed in %s", path.name)

        addon = getattr(mod, "INSTRUCTION_ADDON", "") or ""

        if (decls or callable(dynamic_provider)) and not hasattr(mod, "execute"):
            self._log.warning("Skill %s declares tools but has no execute()", path.name)
            return

        self._skills.append(mod)
        if addon.strip():
            self._instructions.append(addon.strip())
        self._register(mod, decls, path.name)

        self._log.info("Skill loaded: %s (tools: %d)", path.stem, len(decls))

    @property
    def declarations(self) -> list[dict]:
        return self._declarations

    @property
    def instructions(self) -> str:
        return "\n".join(self._instructions)

    def owns(self, tool_name: str) -> bool:
        return tool_name in self._tool_map

    async def execute(self, name: str, args: Any) -> str:
        mod = self._tool_map.get(name)
        if mod is None:
            return f"Unknown tool: {name}"
        return await mod.execute(name, args)

    async def startup(self, db_path: str) -> None:
        """Call init() on every skill, then refresh dynamic tools."""
        for mod in self._skills:
            init_fn = getattr(mod, "init", None)
            if callable(init_fn):
                try:
                    await _maybe_await(init_fn, db_path, self._log)
                except Exception:
                    self._log.exception("init() failed for %s", mod.__name__)

            provider = getattr(mod, "DYNAMIC_DECLARATIONS_PROVIDER", None)
            if callable(provider):
                try:
                    fresh = list(await _maybe_await(provider) or [])
                    added = self._register(mod, fresh, mod.__name__)
                    if added:
                        self._log.info("Dynamic tools from %s: +%d", mod.__name__, added)
                except Exception:
                    self._log.exception("DYNAMIC_DECLARATIONS_PROVIDER failed in %s", mod.__name__)

    async def shutdown(self) -> None:
        """Call shutdown() on skills that define it."""
        for mod in self._skills:
            fn = getattr(mod, "shutdown", None)
            if callable(fn):
                try:
                    await _maybe_await(fn)
                except Exception:
                    self._log.exception("shutdown() failed for %s", mod.__name__)
