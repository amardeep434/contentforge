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
    metadata_system: str
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


def _str(value, label: str, path: Path) -> str:
    if not isinstance(value, str):
        raise MissingDataError(f"{path}: {label} must be a string")
    return value


def _number(value, label: str, path: Path) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MissingDataError(f"{path}: {label} must be a number")
    return float(value)


def _bool(value, label: str, path: Path) -> bool:
    if not isinstance(value, bool):
        raise MissingDataError(f"{path}: {label} must be a boolean (true/false)")
    return value


def _int(value, label: str, path: Path) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MissingDataError(f"{path}: {label} must be an integer")
    return value


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
        name=_str(_require(table, "niche", "name", path), "[niche].name", path),
        title_format=_str(
            _require(table, "niche", "title_format", path), "[niche].title_format", path
        ),
        house_style=_str(
            _require(table, "visual", "house_style", path), "[visual].house_style", path
        ),
        negative=_str(_require(table, "visual", "negative", path), "[visual].negative", path),
        bg=_colour(_require(table, "visual", "bg", path), "[visual].bg", path),
        accent=_colour(_require(table, "visual", "accent", path), "[visual].accent", path),
        image_model=_str(
            _require(table, "visual", "image_model", path), "[visual].image_model", path
        ),
        voice_reference=Path(
            _str(_require(table, "voice", "reference", path), "[voice].reference", path)
        ).expanduser(),
        pace=_number(_require(table, "voice", "pace", path), "[voice].pace", path),
        music=_bool(_require(table, "voice", "music", path), "[voice].music", path),
        script_system=_str(
            _require(table, "script", "system", path), "[script].system", path
        ),
        metadata_system=_str(
            _require(table, "metadata", "system", path), "[metadata].system", path
        ),
        target_words=(
            _int(words[0], "[script].target_words[0]", path),
            _int(words[1], "[script].target_words[1]", path),
        ),
    )
