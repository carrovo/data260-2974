import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

LAST_CONSOLIDATED_PATTERN = re.compile(
    r"<!--\s*last_consolidated:\s*([^>]+?)\s*-->",
    re.IGNORECASE,
)
FACT_PATTERN = re.compile(r"^\s*-\s*([^:]+):\s*(.+?)\s*$")


def utc_now() -> datetime:
    return datetime.now(UTC)


class FileMemoryManager:
    """Load, inspect, update, and consolidate Markdown memory."""

    def __init__(
        self,
        project_root: Path,
        *,
        now_fn=utc_now,
    ) -> None:
        self.project_root = project_root
        self.agent_path = project_root / "AGENT.md"
        self.memory_path = project_root / "MEMORY.md"
        self._now_fn = now_fn

    def load_agent(self) -> str:
        return self.agent_path.read_text(encoding="utf-8").strip()

    def load_memory(self) -> str:
        return self.memory_path.read_text(encoding="utf-8").strip()

    def load_prompt_context(self) -> str:
        return (
            "Durable project instructions:\n"
            f"{self.load_agent()}\n\n"
            "Durable learned facts:\n"
            f"{self.load_memory()}"
        )

    def non_empty_non_comment_lines(self) -> list[str]:
        lines = self.load_memory().splitlines()

        return [
            line.strip()
            for line in lines
            if line.strip()
            and not line.strip().startswith("<!--")
            and not line.strip().startswith("#")
        ]

    def last_consolidated_at(self) -> datetime | None:
        match = LAST_CONSOLIDATED_PATTERN.search(self.load_memory())

        if match is None:
            return None

        raw_value = match.group(1).strip()

        try:
            parsed = datetime.fromisoformat(raw_value)
        except ValueError:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)

        return parsed.astimezone(UTC)

    def consolidation_status(self) -> dict[str, Any]:
        line_count = len(self.non_empty_non_comment_lines())
        last_consolidated = self.last_consolidated_at()
        now = self._now_fn()
        age_exceeded = last_consolidated is None or now - last_consolidated > timedelta(
            hours=24
        )
        line_limit_exceeded = line_count > 40

        reasons: list[str] = []

        if line_limit_exceeded:
            reasons.append("more_than_40_memory_lines")

        if age_exceeded:
            reasons.append("older_than_24_hours")

        return {
            "required": bool(reasons),
            "line_count": line_count,
            "last_consolidated": (
                last_consolidated.isoformat() if last_consolidated else None
            ),
            "reasons": reasons,
        }

    @staticmethod
    def _parse_facts(
        lines: list[str],
    ) -> tuple[
        dict[str, list[str]],
        list[str],
    ]:
        facts: dict[str, list[str]] = {}
        unstructured: list[str] = []

        for line in lines:
            match = FACT_PATTERN.match(line)

            if match is None:
                if line not in unstructured:
                    unstructured.append(line)
                continue

            display_key = match.group(1).strip()
            value = match.group(2).strip()
            normalized_key = display_key.casefold()

            facts.setdefault(normalized_key, [])

            if value not in facts[normalized_key]:
                facts[normalized_key].append(value)

        return facts, unstructured

    def consolidate(self) -> dict[str, Any]:
        before_lines = self.non_empty_non_comment_lines()
        facts, unstructured = self._parse_facts(before_lines)
        resolved: list[dict[str, Any]] = []
        output_lines: list[str] = []

        for key, values in facts.items():
            chosen = values[-1]
            output_lines.append(f"- {key}: {chosen}")

            if len(values) > 1:
                resolved.append(
                    {
                        "key": key,
                        "values_seen": values,
                        "chosen": chosen,
                        "rule": "latest explicit value wins",
                    }
                )

        output_lines.extend(unstructured)

        timestamp = self._now_fn().isoformat()
        document_lines = [
            "# Durable Memory",
            "",
            f"<!-- last_consolidated: {timestamp} -->",
            "",
            "## Current facts",
            "",
            *output_lines,
            "",
            "## Explicit contradiction resolutions",
            "",
        ]

        if resolved:
            for item in resolved:
                replaced = " | ".join(item["values_seen"][:-1])
                document_lines.append(
                    "- resolution_"
                    f"{item['key']}: kept {item['chosen']}; "
                    f"superseded {replaced}; "
                    f"rule={item['rule']}"
                )
        else:
            document_lines.append("- none: no conflicting values were found")

        self.memory_path.write_text(
            "\n".join(document_lines).rstrip() + "\n",
            encoding="utf-8",
        )

        after_count = len(self.non_empty_non_comment_lines())

        return {
            "before": len(before_lines),
            "after": after_count,
            "duplicates_removed": (len(before_lines) - len(output_lines)),
            "contradictions": resolved,
            "under_40_lines": after_count < 40,
        }

    @staticmethod
    def extract_dream_facts(
        recent_messages: list[dict[str, Any]],
    ) -> list[str]:
        markers = (
            "i prefer",
            "my budget",
            "i need",
            "i must",
            "my deadline",
            "remember",
        )
        facts: list[str] = []

        for message in recent_messages:
            if message.get("role") != "user":
                continue

            content = " ".join(str(message.get("content", "")).split())
            lowered = content.casefold()

            if content and any(marker in lowered for marker in markers):
                candidate = f"- learned fact: {content}"

                if candidate not in facts:
                    facts.append(candidate)

            if len(facts) == 3:
                break

        return facts

    def dream(
        self,
        recent_messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        new_facts = self.extract_dream_facts(recent_messages)
        existing = self.load_memory()
        added: list[str] = []

        for fact in new_facts:
            if fact not in existing:
                added.append(fact)

        if added:
            with self.memory_path.open(
                "a",
                encoding="utf-8",
            ) as memory_file:
                memory_file.write(
                    "\n## Facts added by /dream\n\n" + "\n".join(added) + "\n"
                )

        return {
            "added_count": len(added),
            "facts": added,
            "consolidation": self.consolidation_status(),
        }

    def handle_command(
        self,
        command: str,
        recent_messages: list[dict[str, Any]],
    ) -> str:
        normalized = command.strip().casefold()

        if normalized == "/memory":
            status = self.consolidation_status()
            return (
                f"{self.load_memory()}\n\n"
                "Memory status: "
                f"{status['line_count']} lines; "
                f"consolidation_required={status['required']}"
            )

        if normalized == "/compact":
            result = self.consolidate()
            return (
                "MEMORY.md consolidated: "
                f"{result['before']} -> {result['after']} "
                "non-empty, non-comment lines; "
                f"contradictions={len(result['contradictions'])}."
            )

        if normalized == "/dream":
            result = self.dream(recent_messages)
            return f"Dream completed: added {result['added_count']} durable fact(s)."

        if normalized == "/help":
            return (
                "/memory - display durable file memory\n"
                "/compact - deduplicate and consolidate MEMORY.md\n"
                "/dream - extract useful durable facts from recent chat\n"
                "/help - display these commands"
            )

        raise ValueError(f"Unsupported memory command: {command}")
