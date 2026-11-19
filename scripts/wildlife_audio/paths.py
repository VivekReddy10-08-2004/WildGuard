"""Portable paths: reject escape, Windows aliases, links and junctions."""

import re
from pathlib import Path, PurePosixPath, PureWindowsPath


def safe_path(root: Path, relative: str) -> Path:
    """Return a contained path without following a link in any existing component."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("path must use nonempty relative POSIX syntax")
    parts = relative.split("/")
    win = PureWindowsPath(relative)
    if win.drive or win.root or PurePosixPath(relative).is_absolute():
        raise ValueError("path must be relative and must not escape root")
    for part in parts:
        if (
            part in {"", ".", ".."}
            or part[-1:] in {" ", "."}
            or re.search(r'[<>:"|?*\x00-\x1f]', part)
            or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?", part)
        ):
            raise ValueError("unsafe path component; must not escape root")
    root = Path(root).absolute()
    # Also reject a linked root or ancestor, including Windows junctions.
    for component in [root, *root.parents]:
        if component.is_symlink() or component.is_junction():
            raise ValueError("linked storage root")
    candidate = root
    for part in parts:
        candidate = candidate / part
        if candidate.is_symlink() or candidate.is_junction():
            raise ValueError("linked path is not permitted")
        if candidate.is_file() and candidate.stat().st_nlink != 1:
            raise ValueError("hard-linked files are not permitted")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("path must not escape root")
    return candidate
