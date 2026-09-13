"""Server configuration: the GEDCOM directory and safe file-name resolution."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .gedcom.file import GedcomFile

_NAME_RE = re.compile(r"^[^<>:\"/\\|?*\x00-\x1f]+$")


class ConfigError(Exception):
    pass


@dataclass
class Settings:
    root: Path
    _cache: dict[Path, tuple[tuple[int, int], GedcomFile]] = field(default_factory=dict, repr=False)

    # -- file names -----------------------------------------------------------------

    def list_paths(self) -> list[Path]:
        return sorted(p for p in self.root.glob("*.ged") if p.is_file())

    def resolve(self, name: str | None) -> Path:
        """Turn a user-supplied file name into a path inside ``root`` (existing file)."""
        path = self.resolve_new(name) if name else self._only_file()
        if not path.is_file():
            names = ", ".join(p.stem for p in self.list_paths()) or "(none)"
            raise ConfigError(f"No GEDCOM file named {path.stem!r}. Available: {names}")
        return path

    def resolve_new(self, name: str) -> Path:
        """Validate a file name (existing or not) and return its path inside ``root``."""
        stem = name.strip()
        if stem.lower().endswith(".ged"):
            stem = stem[:-4]
        if not stem or stem in (".", "..") or not _NAME_RE.match(stem) or stem != stem.strip("."):
            raise ConfigError(f"Invalid file name {name!r}: use a plain name without path separators")
        path = (self.root / f"{stem}.ged").resolve()
        if path.parent != self.root.resolve():
            raise ConfigError(f"Invalid file name {name!r}")
        return path

    def _only_file(self) -> Path:
        paths = self.list_paths()
        if len(paths) == 1:
            return paths[0]
        if not paths:
            raise ConfigError(f"No .ged files in {self.root}")
        raise ConfigError(
            "Several GEDCOM files are available; pass `file`. Choose from: "
            + ", ".join(p.stem for p in paths)
        )

    # -- loading with cache -----------------------------------------------------------

    def open(self, name: str | None) -> GedcomFile:
        path = self.resolve(name)
        st = path.stat()
        key = (st.st_mtime_ns, st.st_size)
        cached = self._cache.get(path)
        if cached is not None and cached[0] == key:
            return cached[1]
        f = GedcomFile.load(path)
        self._cache[path] = (key, f)
        return f

    def forget(self, path: Path) -> None:
        self._cache.pop(path, None)

    def remember(self, f: GedcomFile) -> None:
        st = f.path.stat()
        self._cache[f.path] = ((st.st_mtime_ns, st.st_size), f)


def settings_from_env() -> Settings:
    raw = os.environ.get("GEDCOM_PATH")
    if not raw:
        raise ConfigError("GEDCOM directory not configured (use --gedcom-path or GEDCOM_PATH)")
    return make_settings(raw)


def make_settings(raw: str) -> Settings:
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise ConfigError(f"GEDCOM path is not a directory: {root}")
    return Settings(root=root)
