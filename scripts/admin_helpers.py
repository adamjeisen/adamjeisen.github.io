"""
Shared helpers for the admin server.

Provides I/O utilities for:
- Markdown files with YAML front matter (news, blog, projects, books)
- YAML data files (socials.yml, coauthors.yml)
- _config.yml targeted editing (preserves comments)
- BibTeX parsing/serialization (publications)
"""

import os
import re
import yaml
from pathlib import Path


# ---------------------------------------------------------------------------
# Markdown front matter
# ---------------------------------------------------------------------------

def parse_markdown(text: str) -> tuple[dict, str]:
    """Parse a markdown file with YAML front matter.

    Returns (metadata_dict, body_string).
    Only splits on the first two '---' delimiters to avoid breaking
    body content that contains '---'.
    """
    if not text.startswith("---"):
        return {}, text

    # Find the closing '---' after the opening one
    end = text.find("---", 3)
    if end == -1:
        return {}, text

    front = text[3:end].strip()
    body = text[end + 3:].lstrip("\n")
    meta = yaml.safe_load(front) or {}
    return meta, body


def serialize_markdown(meta: dict, body: str) -> str:
    """Serialize metadata dict + body back to markdown with front matter."""
    front = yaml.dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return f"---\n{front}---\n{body}"


def read_markdown_file(path: Path) -> dict:
    """Read a markdown file, returning {filename, meta fields..., body}."""
    text = path.read_text(encoding="utf-8")
    meta, body = parse_markdown(text)
    result = {"filename": path.name, **meta, "body": body}
    return result


def write_markdown_file(path: Path, data: dict):
    """Write a markdown file from a dict with 'body' and metadata keys."""
    body = data.pop("body", "")
    data.pop("filename", None)
    text = serialize_markdown(data, body)
    path.write_text(text, encoding="utf-8")


def list_markdown_dir(dirpath: Path) -> list[dict]:
    """List all .md files in a directory, parsed."""
    if not dirpath.exists():
        return []
    items = []
    for f in sorted(dirpath.glob("*.md")):
        items.append(read_markdown_file(f))
    return items


# ---------------------------------------------------------------------------
# YAML files
# ---------------------------------------------------------------------------

def read_yaml(path: Path) -> dict:
    """Read a YAML file, returning a dict."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text) or {}


def write_yaml(path: Path, data: dict):
    """Write a dict to a YAML file."""
    text = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    path.write_text(text, encoding="utf-8")


def read_yaml_with_comments(path: Path) -> str:
    """Read a YAML file as raw text (preserving comments)."""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_yaml_raw(path: Path, text: str):
    """Write raw text to a YAML file (preserving comments)."""
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# _config.yml targeted editing
# ---------------------------------------------------------------------------

def read_config_field(config_text: str, key: str) -> str:
    """Extract a value for a top-level key from _config.yml text.

    Handles both single-line values and multi-line '>' block scalars.
    """
    # Try multi-line block scalar (key: >\n  value) — also allows comment after >
    pattern = rf"^{re.escape(key)}:\s*>.*\n((?:[ \t]+.*\n?)*)"
    m = re.search(pattern, config_text, re.MULTILINE)
    if m:
        lines = m.group(1).strip().splitlines()
        return "\n".join(line.strip() for line in lines)

    # Single-line value
    pattern = rf"^{re.escape(key)}:\s*(.+)$"
    m = re.search(pattern, config_text, re.MULTILINE)
    if m:
        val = m.group(1).strip()
        # Strip inline YAML comment (but not # inside quotes or HTML)
        if " #" in val and not val.startswith('"') and not val.startswith("'") and "<" not in val:
            val = val[:val.index(" #")].strip()
        return val

    return ""


def update_config_field(config_text: str, key: str, value: str) -> str:
    """Update a top-level key in _config.yml text, preserving structure.

    Handles single-line values. For block scalars (>), rewrites as single-line
    if the value fits, or as block scalar if it contains HTML/newlines.
    """
    # Check if key currently uses block scalar
    block_pattern = rf"^({re.escape(key)}:\s*)>\s*\n((?:[ \t]+.*\n?)*)"
    m = re.search(block_pattern, config_text, re.MULTILINE)
    if m:
        # Replace block scalar with new value
        if "\n" in value or "<" in value:
            # Keep as block scalar
            indented = "  " + value.replace("\n", "\n  ")
            replacement = f"{m.group(1)}>\n{indented}\n"
        else:
            replacement = f"{m.group(1)}>\n  {value}\n"
        return config_text[:m.start()] + replacement + config_text[m.end():]

    # Single-line replacement
    pattern = rf"^({re.escape(key)}:\s*)(.+)$"
    m = re.search(pattern, config_text, re.MULTILINE)
    if m:
        return config_text[:m.start()] + f"{m.group(1)}{value}" + config_text[m.end():]

    return config_text


# ---------------------------------------------------------------------------
# BibTeX (regex-based, preserves file order)
# ---------------------------------------------------------------------------

BIBTEX_JEKYLL_HEADER = "---\n---\n\n"

# Matches @type{key, ... } allowing nested braces in field values
_BIB_ENTRY_RE = re.compile(
    r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)\n\}",
    re.DOTALL,
)

# Matches field = {value} or field = "value" or field = number
_BIB_FIELD_RE = re.compile(
    r"(\w+)\s*=\s*(?:\{((?:[^{}]|\{[^{}]*\})*)\}|\"([^\"]*)\"|(\d+))",
    re.DOTALL,
)


def read_bib(path: Path) -> list[dict]:
    """Parse a .bib file into a list of entry dicts, preserving file order.

    Each dict has keys: entry_type, key, and all BibTeX fields.
    Strips Jekyll front matter (---\\n---) before parsing.
    """
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    # Strip Jekyll front matter
    if text.startswith("---"):
        idx = text.find("---", 3)
        if idx != -1:
            text = text[idx + 3:].lstrip("\n")

    entries = []
    for m in _BIB_ENTRY_RE.finditer(text):
        entry_type = m.group(1).lower()
        key = m.group(2).strip()
        body = m.group(3)
        d = {"entry_type": entry_type, "key": key}
        for fm in _BIB_FIELD_RE.finditer(body):
            field_name = fm.group(1).lower()
            value = fm.group(2) if fm.group(2) is not None else (fm.group(3) if fm.group(3) is not None else fm.group(4))
            if value is not None:
                # Collapse internal whitespace runs (from multi-line values)
                value = re.sub(r"\s+", " ", value).strip()
                # Strip nested braces from simple values like {{true}}
                while value.startswith("{") and value.endswith("}"):
                    value = value[1:-1]
            d[field_name] = value
        entries.append(d)
    return entries


def write_bib(path: Path, entries: list[dict]):
    """Write entries back to a .bib file with Jekyll front matter.

    Preserves the order of the entries list.
    """
    parts = []
    for d in entries:
        entry_type = d.get("entry_type", "article")
        key = d.get("key", "unknown")
        fields = []
        for k, v in d.items():
            if k in ("entry_type", "key"):
                continue
            if v is None:
                continue
            # Use braces for all values
            fields.append(f"  {k} = {{{v}}}")
        body = ",\n".join(fields)
        parts.append(f"@{entry_type}{{{key},\n{body}\n}}")
    text = "\n\n".join(parts) + "\n"
    path.write_text(BIBTEX_JEKYLL_HEADER + text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Filename utils
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "untitled"
