"""Per-niche production profile, loaded from data/<niche>/niche.toml.

One niche = one look, voice and title format. The profile is hand-authored for
now (auto-deriving it from a reference channel is parked - see the niche-structure
spec). Values are validated at load so a wrong-looking niche fails loudly rather
than rendering off-brand.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from contentforge.errors import MissingDataError

NICHE_FILE = "niche.toml"


@dataclass(frozen=True)
class NicheConfig:
    name: str
    title_format: str
    house_style: str
    negative: str
    bg: tuple[int, int, int]
    accent: tuple[int, int, int]
    image_model: str
    voice_reference: Path
    pace: float
    music: bool
    script_system: str
    target_words: tuple[int, int]


def _require(table: dict, section: str, key: str, path: Path):
    if section not in table or key not in table[section]:
        raise MissingDataError(
            f"{path}: missing [{section}].{key} - a niche profile must set it"
        )
    return table[section][key]


def _colour(value, label: str, path: Path) -> tuple[int, int, int]:
    if not (isinstance(value, list) and len(value) == 3
            and all(isinstance(c, int) for c in value)):
        raise MissingDataError(f"{path}: {label} must be three integers [r, g, b]")
    return (value[0], value[1], value[2])


def load_niche(niche: str, root: Path) -> NicheConfig:
    path = Path(root) / niche / NICHE_FILE
    if not path.exists():
        raise MissingDataError(
            f"no niche.toml at {path}; create it (see docs/setup/niches.md)"
        )
    with path.open("rb") as handle:
        table = tomllib.load(handle)

    words = _require(table, "script", "target_words", path)
    if not (isinstance(words, list) and len(words) == 2):
        raise MissingDataError(f"{path}: [script].target_words must be [low, high]")

    return NicheConfig(
        name=_require(table, "niche", "name", path),
        title_format=_require(table, "niche", "title_format", path),
        house_style=_require(table, "visual", "house_style", path),
        negative=_require(table, "visual", "negative", path),
        bg=_colour(_require(table, "visual", "bg", path), "[visual].bg", path),
        accent=_colour(_require(table, "visual", "accent", path), "[visual].accent", path),
        image_model=_require(table, "visual", "image_model", path),
        voice_reference=Path(_require(table, "voice", "reference", path)).expanduser(),
        pace=float(_require(table, "voice", "pace", path)),
        music=bool(_require(table, "voice", "music", path)),
        script_system=_require(table, "script", "system", path),
        target_words=(int(words[0]), int(words[1])),
    )
