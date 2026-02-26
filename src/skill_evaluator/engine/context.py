"""Context file injection — resolve, read, and build synthetic messages."""

from __future__ import annotations

from pathlib import Path

from skill_evaluator.config.schema import (
    ContextFileConfig,
    MessageConfig,
    ToolCallConfig,
)


class ContextFileError(Exception):
    """Raised when a context file cannot be resolved or read."""


def resolve_context_file(eval_file: Path, file_ref: str) -> Path:
    """Resolve a context file path relative to the eval file's directory."""
    base_dir = Path(eval_file).parent
    resolved = (base_dir / file_ref).resolve()
    if not resolved.exists():
        raise ContextFileError(f"Context file not found: {file_ref} (resolved to {resolved})")
    if not resolved.is_file():
        raise ContextFileError(f"Context path is not a file: {file_ref} (resolved to {resolved})")
    return resolved


def read_context_file(path: Path, lines: list[int] | None = None) -> str:
    """Read a file and format with cat -n style line numbers.

    If *lines* is ``[start, end]`` (1-indexed, inclusive), only those lines
    are returned.  The range is clamped to the actual file length.
    """
    try:
        all_lines = path.read_text().splitlines()
    except UnicodeDecodeError as e:
        raise ContextFileError(f"Cannot read binary file: {path} ({e})") from e

    if lines is not None:
        start, end = lines[0], lines[1]
        if start > len(all_lines):
            return f"(file has {len(all_lines)} lines; requested start {start} is beyond end)"
        # Clamp end to file length
        end = min(end, len(all_lines))
        selected = all_lines[start - 1 : end]
        start_offset = start
    else:
        selected = all_lines
        start_offset = 1

    numbered = []
    for i, line in enumerate(selected, start=start_offset):
        numbered.append(f"     {i}\t{line}")
    return "\n".join(numbered)


def build_context_messages(
    eval_file: Path,
    context_files: list[ContextFileConfig],
) -> list[MessageConfig]:
    """Build synthetic Read tool-call messages for context files.

    Returns 3 MessageConfig objects:
      1. user: "[Reading context files]"
      2. assistant: text + batched Read tool_calls
      3. One tool_result per file (consecutive — will be merged by build_messages)
    """
    if not context_files:
        return []

    # Resolve and read all files first (fail fast on errors)
    resolved: list[tuple[Path, ContextFileConfig]] = []
    for ctx in context_files:
        path = resolve_context_file(eval_file, ctx.file)
        resolved.append((path, ctx))

    # 1. User message
    user_msg = MessageConfig(role="user", content="[Reading context files]")

    # 2. Assistant message with batched Read tool_calls
    tool_calls: list[ToolCallConfig] = []
    for i, (path, ctx) in enumerate(resolved):
        tool_id = f"ctx_{i + 1:04d}"
        read_input: dict = {"file_path": str(path)}
        if ctx.lines is not None:
            read_input["offset"] = ctx.lines[0]
            read_input["limit"] = ctx.lines[1] - ctx.lines[0] + 1
        tool_calls.append(ToolCallConfig(id=tool_id, name="Read", input=read_input))

    assistant_msg = MessageConfig(
        role="assistant",
        content="I'll read the relevant files.",
        tool_calls=tool_calls,
    )

    # 3. Tool results
    tool_results: list[MessageConfig] = []
    for i, (path, ctx) in enumerate(resolved):
        tool_id = f"ctx_{i + 1:04d}"
        content = read_context_file(path, ctx.lines)
        tool_results.append(
            MessageConfig(
                role="tool_result",
                tool_use_id=tool_id,
                content=content,
            )
        )

    return [user_msg, assistant_msg, *tool_results]
