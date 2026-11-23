"""Recognise Darkest Dungeon MODs and preserve nested collection parents.

MOD game asset directories (campaign, town, heroes...) must never be promoted
into collection nodes. Independent library folders may contain nested folders
with multiple actual MODs; these stay under their parent, with independent
UI expansion state. Pure Python, no Qt or Steam required.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_ASSET_ROOTS = frozenset((
    "heroes", "monsters", "shared", "localization", "fx", "campaign",
    "dungeons", "trinkets", "raid", "effects", "inventory", "panels",
    "upgrades", "town", "modes", "scripts", "colours", "audio",
    "map", "maps", "fonts", "portraits", "bank", "banks", "overlays",
    "animation", "animations", "anim", "strings", "loot", "rules",
    "quests", "features", "events", "curios", "skills", "sound",
    "sounds", "music", "dialogue", "video", "videos", "textures",
    "dlc", "loading_screen", "loading_screens", "quirks", "diseases", "camping", "fe_flow",
))
_SKIP_NAMES = frozenset((
    ".venv", "venv", "__pycache__", "node_modules", "dist", "build",
    ".git", ".idea", "_windows", "_linux", "_osx",
))
_MARKERS = ("preview_icon.png", "project.xml", "modfiles.txt")


@dataclass(frozen=True)
class LibraryGroup:
    folder: Path
    mods: tuple[Path, ...]
    parent: Path | None = None


def _child_dirs(folder: Path) -> list[Path]:
    try:
        return sorted(
            (p for p in folder.iterdir()
             if p.is_dir() and not p.name.startswith(".")
             and p.name.casefold() not in _SKIP_NAMES),
            key=lambda p: p.name.casefold(),
        )
    except OSError:
        return []


def _has_game_assets(folder: Path) -> bool:
    """Immediate gameplay directories distinguish real MODs from a library.

    A MOD's own ``campaign/town`` folders are assets, NOT more MODs.
    """
    return any(p.name.casefold() in _ASSET_ROOTS for p in _child_dirs(folder))


def looks_like_mod(folder: Path) -> bool:
    """Recognise a single MOD without recursively mining nested source IDs."""
    if not folder.is_dir():
        return False
    if any((folder / marker).is_file() for marker in _MARKERS):
        return True
    return _has_game_assets(folder)


def _direct_mod_children(folder: Path) -> list[Path]:
    """Exclude reserved game content folders before MOD classification.

    For example a ``campaign`` folder can itself contain a ``town`` folder,
    which used to make it look like a complete child MOD.
    """
    return [
        child for child in _child_dirs(folder)
        if child.name.casefold() not in _ASSET_ROOTS and looks_like_mod(child)
    ]


def discover_mod_groups(folder: Path) -> list[LibraryGroup]:
    """Discover leaves and nested collections, without flattening ancestry.

    A genuine MOD with game-asset folders is always a leaf. A directory with
    multiple MOD-like children is a collection, including a numbered directory
    such as ``801 ...`` containing two independently uploadable skin variants.

    Only uploadable leaves appear in ``LibraryGroup.mods``; directories are
    grouping metadata. Wrappers with no direct MOD children are bypassed, so
    choosing a directory *above* ``mods`` still displays ``mods`` as the root.
    Depth is bounded to avoid traversing arbitrary non-MOD file trees.
    """
    root = folder.expanduser().resolve()
    if not root.is_dir():
        return []

    if _has_game_assets(root):
        return [LibraryGroup(root, (root,))]

    def visit(container: Path, depth: int = 0) -> list[LibraryGroup]:
        if depth > 4:
            return []
        direct: list[Path] = []
        nested: list[LibraryGroup] = []

        for child in _child_dirs(container):
            # These are subdirectories of game resources, never MOD folders.
            if child.name.casefold() in _ASSET_ROOTS:
                continue
            if _has_game_assets(child):
                direct.append(child)
                continue
            # Detect one or more child MODs before treating a wrapper's stale
            # preview/project files as evidence that the wrapper is itself a MOD.
            submods = _direct_mod_children(child)
            if submods:
                nested.extend(visit(child, depth + 1))
            elif looks_like_mod(child):
                direct.append(child)
            elif depth < 4:
                # A plain wrapper may contain another plain wrapper before
                # the actual MOD directory. No files are changed by scanning.
                nested.extend(visit(child, depth + 1))

        if direct:
            # When this container owns direct MOD leaves, it also owns its
            # immediate child collection groups. Nested groups manage their
            # own expansion state rather than opening with their parent.
            attached = [
                LibraryGroup(g.folder, g.mods,
                             container if g.parent is None else g.parent)
                for g in nested
            ]
            return [LibraryGroup(container, tuple(direct))] + attached
        return nested

    found = visit(root)
    if not found and looks_like_mod(root):
        found = [LibraryGroup(root, (root,))]

    # No MOD leaf may be submitted twice even when multiple wrappers alias it.
    seen: set[Path] = set()
    groups: list[LibraryGroup] = []
    for group in found:
        leaves = tuple(p for p in group.mods if p not in seen)
        seen.update(leaves)
        if leaves:
            groups.append(LibraryGroup(group.folder, leaves, group.parent))
    return groups
