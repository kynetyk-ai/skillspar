"""Built-in Claude Code tool schemas."""

from __future__ import annotations

_BUILTINS: dict[str, dict] = {
    "Read": {
        "name": "Read",
        "description": "Read the contents of a file at the given path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute path to the file to read.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of lines to read.",
                },
            },
            "required": ["file_path"],
        },
    },
    "Write": {
        "name": "Write",
        "description": "Write content to a file, creating or overwriting it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute path to the file to write.",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file.",
                },
            },
            "required": ["file_path", "content"],
        },
    },
    "Edit": {
        "name": "Edit",
        "description": "Perform exact string replacements in a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute path to the file to modify.",
                },
                "old_string": {
                    "type": "string",
                    "description": "The text to replace.",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement text.",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    "Bash": {
        "name": "Bash",
        "description": "Execute a bash command and return its output.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The command to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Optional timeout in milliseconds.",
                },
            },
            "required": ["command"],
        },
    },
    "Glob": {
        "name": "Glob",
        "description": "Find files matching a glob pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The glob pattern to match files against.",
                },
                "path": {
                    "type": "string",
                    "description": "The directory to search in.",
                },
            },
            "required": ["pattern"],
        },
    },
    "Grep": {
        "name": "Grep",
        "description": "Search file contents using a regex pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The regex pattern to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search in.",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob pattern to filter files.",
                },
            },
            "required": ["pattern"],
        },
    },
}


def get_builtin_tool(name: str) -> dict:
    """Return the API-ready tool definition for a built-in tool.

    Raises ``KeyError`` if *name* is not a known built-in.
    """
    try:
        return _BUILTINS[name]
    except KeyError:
        raise KeyError(f"Unknown built-in tool: {name}") from None
