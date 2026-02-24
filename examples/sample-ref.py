"""Sample reference file used by context.eval.yaml to demonstrate context injection."""


def greet(name: str) -> str:
    """Return a personalised greeting."""
    return f"Hello, {name}! Welcome aboard."


def farewell(name: str) -> str:
    """Return a farewell message."""
    return f"Goodbye, {name}. See you next time!"
