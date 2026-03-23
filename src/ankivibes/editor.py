"""Editor format for definitions — serialize/parse for $EDITOR editing."""
from __future__ import annotations

from typing import Any


def definitions_to_text(lemma: str, pos: str | None, definitions: list[dict[str, Any]]) -> str:
    """Serialize definitions to a human-editable text format."""
    lines: list[str] = []
    lines.append(f"# {lemma} ({pos or 'unknown'})")
    lines.append("# Edit definitions below. Lines starting with # are comments.")
    lines.append("# Format: definition text, then indented examples with optional translations.")
    lines.append("# Indented lines starting with > are translations of the preceding example.")
    lines.append("")

    for defn in definitions:
        lines.append(defn.get("text", ""))
        for ex in defn.get("examples", []):
            text = ex.get("text", "")
            translation = ex.get("translation")
            if text:
                lines.append(f"  {text}")
            if translation:
                lines.append(f"  > {translation}")
        lines.append("")

    return "\n".join(lines)


def text_to_definitions(text: str) -> list[dict[str, Any]]:
    """Parse the editor text format back into a definitions list."""
    definitions: list[dict[str, Any]] = []
    current_def: dict[str, Any] | None = None
    current_examples: list[dict[str, str | None]] = []

    for line in text.splitlines():
        stripped = line.strip()

        # Skip comments and blank lines between definitions
        if stripped.startswith("#"):
            continue

        if not stripped:
            # Blank line — finalize current definition if any
            if current_def is not None:
                current_def["examples"] = current_examples
                definitions.append(current_def)
                current_def = None
                current_examples = []
            continue

        if line.startswith(("  ", "\t")):
            # Indented line — example or translation
            if stripped.startswith("> "):
                # Translation of the last example
                translation = stripped[2:]
                if current_examples:
                    current_examples[-1]["translation"] = translation
            else:
                # Example text
                current_examples.append({"text": stripped, "translation": None})
        else:
            # Non-indented, non-comment line — new definition
            if current_def is not None:
                current_def["examples"] = current_examples
                definitions.append(current_def)
                current_examples = []
            current_def = {"text": stripped, "pos": None}

    # Finalize last definition
    if current_def is not None:
        current_def["examples"] = current_examples
        definitions.append(current_def)

    return definitions
