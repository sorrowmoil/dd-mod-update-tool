"""Darkest Dungeon Workshop Studio - archive and upload core.

All Steam uploader operations are performed on independent copies of the MODs.
The original PublishedFileId is *never* written as the new upload ID.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Callable
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

_FALLBACK_UPLOADER = Path(
    r"F:\SteamLibrary\steamapps\common\DarkestDungeon\_windows\win32\steam_workshop_upload.exe"
)


def detect_steam_root() -> Path | None:
    """Locate Steam installation root via Windows registry or common paths."""
    candidates: list[Path] = []
    if os.name == "nt":
        try:
            import winreg
            reg_locs = (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", ("SteamPath", "InstallPath")),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", ("InstallPath",)),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", ("InstallPath",)),
            )
            for hive, subkey, names in reg_locs:
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        for name in names:
                            try:
                                raw, _ = winreg.QueryValueEx(key, name)
                                if isinstance(raw, str) and raw.strip():
                                    candidates.append(Path(raw.strip()))
                            except OSError:
                                pass
                except OSError:
                    pass
        except ImportError:
            pass
    candidates.extend([
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Steam",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Steam",
    ])
    for drv in "CDEFGH":
        candidates.append(Path(f"{drv}:\\Steam"))
    for p in candidates:
        try:
            rp = p.expanduser().resolve()
            if (rp / "steam.exe").is_file() or (rp / "steamapps").is_dir():
                return rp
        except OSError:
            continue
    return None


def discover_steam_libraries(steam_root: Path | None = None) -> list[Path]:
    """Parse libraryfolders.vdf and return all existing Steam library roots."""
    root = steam_root or detect_steam_root()
    raw_libs: list[Path] = []
    if root is not None:
        raw_libs.append(root)
        for vdf in (root / "steamapps" / "libraryfolders.vdf", root / "config" / "libraryfolders.vdf"):
            if not vdf.is_file():
                continue
            try:
                content = vdf.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in re.finditer(r'"path"\s+"([^"]+)"', content, re.IGNORECASE):
                raw_libs.append(Path(m.group(1).replace("\\\\", "\\")))
            for m in re.finditer(r'^\s*"[0-9]+"\s+"([^"]+)"', content, re.MULTILINE):
                raw_libs.append(Path(m.group(1).replace("\\\\", "\\")))
    for drv in "CDEFGH":
        raw_libs.append(Path(f"{drv}:\\SteamLibrary"))
        raw_libs.append(Path(f"{drv}:\\Steam"))
    unique: list[Path] = []
    seen: set[str] = set()
    for p in raw_libs:
        try:
            rp = p.expanduser().resolve()
            key = str(rp).casefold()
            if key not in seen and rp.is_dir():
                seen.add(key)
                unique.append(rp)
        except OSError:
            continue
    return unique


def detect_workshop_uploader() -> Path | None:
    """Locate Darkest Dungeon steam_workshop_upload.exe across Steam libraries."""
    for lib in discover_steam_libraries():
        install_dirs = ["DarkestDungeon"]
        acf = lib / "steamapps" / "appmanifest_262060.acf"
        if acf.is_file():
            try:
                txt = acf.read_text(encoding="utf-8", errors="replace")
                if m := re.search(r'"installdir"\s+"([^"]+)"', txt, re.IGNORECASE):
                    dname = m.group(1).strip()
                    if dname and dname not in install_dirs:
                        install_dirs.insert(0, dname)
            except OSError:
                pass
        for dname in install_dirs:
            common = lib / "steamapps" / "common" / dname
            for rel in (
                Path("_windows") / "win32" / "steam_workshop_upload.exe",
                Path("_windows") / "steam_workshop_upload.exe",
            ):
                exe = common / rel
                if exe.is_file():
                    return exe
    return None


DEFAULT_UPLOADER = detect_workshop_uploader() or _FALLBACK_UPLOADER
DEFAULT_WORKSPACE = Path.home() / "Documents" / "DDWorkshopStudio_Archive"
WORKSHOP_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id={}"
WORKSHOP_TAG_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("GENERAL", ("Gameplay Tweaks", "Overhauls", "Trinkets", "Monsters", "Localization", "UI")),
    ("CLASS MODS", ("New Class", "Class Tweaks", "Skins")),
)
WORKSHOP_TAGS: tuple[str, ...] = tuple(t for _, grp in WORKSHOP_TAG_GROUPS for t in grp)
_TAG_CANONICAL = {t.casefold(): t for t in WORKSHOP_TAGS}
VALID_ID = re.compile(r"[1-9][0-9]{6,12}\Z")
INVALID_SENTINEL_IDS = frozenset(("0", "18446744073709551615"))
SOURCE_ID_TAGS = {"publishedfileid", "workshopid", "steamworkshopid", "workshopitemid"}
IGNORE_ROOT = {
    "project.xml", "workshop_upload.xml", "steam_workshop_uploader.log",
    "modfiles.txt", "repair_701.xml", "repair_701_new.xml",
}
MAX_PREVIEW_BYTES = 900_000


def project_key(source: Path) -> str:
    fingerprint = sha256(str(source.resolve()).casefold().encode("utf-8")).hexdigest()[:10]
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", source.name).strip(" .")[:65]
    return f"{safe or 'MOD'}_{fingerprint}"


def project_dir(workspace: Path, source: Path) -> Path:
    return workspace / "projects" / project_key(source)


_INVISIBLE_CHARS = frozenset("\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2060\ufeff")


def _clean_text(text: str) -> str:
    # XML 1.0 permits CR, LF and TAB, not arbitrary C0 control characters or copy-pasted invisible marks.
    return "".join(c for c in text if (c in "\n\r\t" or ord(c) >= 32) and c not in _INVISIBLE_CHARS)


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + ".tmp")
    pending.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    pending.replace(path)


def _scan_mod_tree(source: Path) -> tuple[str, list[Path]]:
    """Single-pass os.walk collecting content fingerprint and project.xml paths."""
    root = source.resolve()
    root_str = str(root)
    h = sha256()
    items: list[tuple[str, int]] = []
    project_xmls: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root_str, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
        rel_dir = os.path.relpath(dirpath, root_str)
        is_root = (rel_dir == ".")
        for fname in filenames:
            low = fname.casefold()
            fpath = os.path.join(dirpath, fname)
            if low == "project.xml":
                project_xmls.append(Path(fpath))
            if is_root and low in IGNORE_ROOT:
                continue
            rel_posix = fname if is_root else f"{rel_dir.replace(os.sep, '/')}/{fname}"
            try:
                items.append((rel_posix.casefold(), os.stat(fpath).st_size))
            except OSError:
                continue
    items.sort()
    for rel_str, size in items:
        h.update(f"{rel_str}:{size}\n".encode("utf-8"))
    return (h.hexdigest()[:16] if items else ""), project_xmls


def scan_origin_ids(source: Path, project_xmls: list[Path] | None = None) -> dict[str, list[str]]:
    """Find potential source Workshop IDs in the original MOD's project XMLs."""
    result: dict[str, list[str]] = {}
    candidates = project_xmls if project_xmls is not None else [
        p for p in source.rglob("*.xml") if p.name.casefold() == "project.xml"
    ]
    for xml_path in candidates:
        try:
            root = ET.parse(xml_path).getroot()
        except (ET.ParseError, UnicodeError, OSError):
            continue
        if root.tag.rsplit("}", 1)[-1].casefold() != "project":
            continue
        rel = str(xml_path.relative_to(source))
        for node in root.iter():
            if not isinstance(node.tag, str):
                continue
            key = node.tag.rsplit("}", 1)[-1].casefold()
            if key in SOURCE_ID_TAGS:
                candidate = (node.text or "").strip()
                if VALID_ID.fullmatch(candidate):
                    result.setdefault(candidate, [])
                    if rel not in result[candidate]:
                        result[candidate].append(rel)
            # Some project XMLs provide a source URL instead of a numeric ID.
            if "url" in key or "link" in key:
                for candidate in re.findall(
                    r"steamcommunity\.com/sharedfiles/filedetails/\?id=([1-9][0-9]{6,12})",
                    node.text or "", re.IGNORECASE,
                ):
                    result.setdefault(candidate, [])
                    if rel not in result[candidate]:
                        result[candidate].append(rel)
    return dict(sorted(result.items(), key=lambda entry: int(entry[0])))


def normalize_tags(raw_tags) -> list[str]:
    if not isinstance(raw_tags, (list, tuple, set)):
        return []
    picked = {_TAG_CANONICAL[str(t).strip().casefold()] for t in raw_tags if str(t).strip().casefold() in _TAG_CANONICAL}
    return [t for t in WORKSHOP_TAGS if t in picked]


def scan_origin_tags(source: Path) -> list[str]:
    """Extract known Workshop tags from root project.xml if present."""
    xml_path = next((p for p in source.iterdir() if p.is_file() and p.name.casefold() == "project.xml"), None)
    if xml_path is None:
        return []
    try:
        root = ET.parse(xml_path).getroot()
    except (ET.ParseError, UnicodeError, OSError):
        return []
    found: list[str] = []
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        if node.tag.rsplit("}", 1)[-1].casefold() in ("tags", "tag") and node.text:
            found.append(node.text.strip())
    return normalize_tags(found)


def source_note(ids: dict[str, list[str]]) -> str:
    if not ids:
        return ""
    urls = "\n".join(WORKSHOP_URL.format(value) for value in ids)
    if len(ids) == 1:
        return (
            "【原 Steam 创意工坊备份】\n"
            "本 MOD 是以下原始工坊条目的私人备份：\n"
            f"{urls}\n"
            "（来源 ID 提取自原始 project.xml，链接有效性及归属尚未独立验证。）"
        )
    return (
        "【候选原始工坊来源，待核实】\n"
        "原始 XML 中发现多个不同的工坊 ID，请确认对应关系：\n"
        f"{urls}"
    )


def read_own_id(xml_path: Path) -> str:
    if not xml_path.is_file():
        return ""
    try:
        root = ET.parse(xml_path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise RuntimeError(f"无法解析已存在的上传配置：{xml_path}\n{exc}") from exc
    value = (root.findtext("PublishedFileId") or "").strip()
    if not value or value in INVALID_SENTINEL_IDS:
        return ""
    if not VALID_ID.fullmatch(value):
        raise RuntimeError(f"上传 XML 含无效 PublishedFileId：{value}")
    return value


def _sanitize_sentinel_id(xml_path: Path) -> str:
    if not xml_path.is_file():
        return ""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except (OSError, ET.ParseError):
        return ""
    node = root.find("PublishedFileId")
    if node is not None:
        val = (node.text or "").strip()
        if val in INVALID_SENTINEL_IDS:
            root.remove(node)
            pending = xml_path.with_name(xml_path.name + ".tmp")
            ET.indent(tree, space="    ")
            tree.write(pending, encoding="utf-8", xml_declaration=True)
            pending.replace(xml_path)
            return val
    return ""


def mod_content_fingerprint(source: Path) -> str:
    """Fast structural fingerprint (relative path + size) ignoring uploader metadata."""
    h = sha256()
    root = source.resolve()
    items: list[tuple[str, int]] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if len(rel.parts) == 1 and rel.name.casefold() in IGNORE_ROOT:
            continue
        try:
            items.append((rel.as_posix().casefold(), p.stat().st_size))
        except OSError:
            continue
    items.sort()
    for rel_str, size in items:
        h.update(f"{rel_str}:{size}\n".encode("utf-8"))
    return h.hexdigest()[:16] if items else ""


@dataclass
class ModEntry:
    source: Path
    title: str
    note: str
    original_ids: dict[str, list[str]] = field(default_factory=dict)
    selected: bool = True
    own_id: str = ""
    status: str = "未归档"
    source_preview_bytes: int = 0
    content_fingerprint: str = ""
    tags: list[str] = field(default_factory=list)


def load_entry(source: Path, workspace: Path) -> ModEntry:
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(str(source))
    fp, project_xmls = _scan_mod_tree(source)
    detected = scan_origin_ids(source, project_xmls)
    folder = project_dir(workspace, source)
    draft = _read_json(folder / "draft.json")
    own_id = read_own_id(folder / "upload.xml")
    state = _read_json(folder / "status.json")
    preview = source / "preview_icon.png"
    preview_bytes = preview.stat().st_size if preview.exists() else 0
    return ModEntry(
        source=source,
        title=_normalize_single_line(str(draft.get("title", source.name))),
        note=str(draft.get("note", source_note(detected))),
        original_ids=detected,
        selected=bool(draft.get("selected", True)),
        own_id=own_id,
        status=str(state.get("status", "待归档")),
        source_preview_bytes=preview_bytes,
        content_fingerprint=fp,
        tags=normalize_tags(draft["tags"]) if isinstance(draft.get("tags"), list) else scan_origin_tags(source),
    )


def save_draft(workspace: Path, item: ModEntry) -> None:
    write_json(project_dir(workspace, item.source) / "draft.json", {
        "source": str(item.source), "title": item.title,
        "note": item.note, "selected": item.selected,
        "tags": normalize_tags(item.tags),
    })


_URL_SPAN_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_UNIT_WORDS = frozenset((
    "个", "项", "条", "张", "种", "格", "级", "层", "次", "天", "年", "月", "日",
    "小时", "分钟", "秒", "倍", "点", "位", "名", "件", "套", "份", "页", "行",
    "章", "节", "回合", "血", "伤", "防", "速", "闪", "暴", "字节", "字", "版",
    "slot", "slots", "kb", "mb", "gb", "kib", "mib", "gib", "px", "fps", "hp", "dmg",
))
_UNIT_FIRST_CHARS = frozenset("个项条张种格级层次天年月日倍点位名件套份页行章节")
_NOTE_IDX_RE = re.compile(
    r"(?:^|(?<=[\s\u4e00-\u9fff（(【「《,，;；:：/]))"
    r"(\d{1,4})"
    r"(?:[\s_、]+|\s*[-.:：]\s*|(?=[「【（(\[《]))"
    r"(?=([^\s\d%‰°.,，;；:：)\]】」》/]+))"
)


def _normalize_single_line(text: str) -> str:
    return re.sub(r"[\r\n\t]+", " ", _clean_text(text)).strip()


def strip_title_index(title: str) -> str:
    cleaned = _normalize_single_line(title)
    m = re.match(r"^(\d{1,4})(?:[\s_、]+|\s*[-.:：·|/]\s*|(?=[「【（(\[《]))(.+)$", cleaned, re.DOTALL)
    if m and 0 <= int(m.group(1)) <= 1000:
        rest = m.group(2).strip()
        if rest:
            return rest
    return cleaned


def _strip_note_segment(seg: str) -> str:
    def _repl(m: re.Match) -> str:
        num = int(m.group(1))
        if num > 1000:
            return m.group(0)
        start = m.start(1)
        if seg[:start].rstrip().endswith("第"):
            return m.group(0)
        nxt = m.group(2)
        low_nxt = nxt.casefold()
        if (
            low_nxt in _UNIT_WORDS
            or nxt[0] in _UNIT_FIRST_CHARS
            or low_nxt.startswith(("回合", "字节", "小时", "分钟"))
        ):
            return m.group(0)
        return ""
    return _NOTE_IDX_RE.sub(_repl, seg)


def strip_note_indices(note: str) -> str:
    parts: list[str] = []
    last = 0
    for m in _URL_SPAN_RE.finditer(note):
        parts.append(_strip_note_segment(note[last:m.start()]))
        parts.append(m.group(0))
        last = m.end()
    parts.append(_strip_note_segment(note[last:]))
    return "".join(parts)


_TITLE_V2_RE = re.compile(
    r"(?:(?:[\s_\-\u00b7]+|(?<=[\u4e00-\u9fff]))v2|[\s_\-]*[（(\[\u3010]\s*v2\s*[）)\]\u3011])\s*\Z",
    re.IGNORECASE,
)
_NOTE_V2_RE = re.compile(
    r"(?:(?:[\s_\-\u00b7]+|(?<=[\u4e00-\u9fff]))v2(?![0-9A-Za-z._])|[\s_\-]*[（(\[\u3010]\s*v2\s*[）)\]\u3011])",
    re.IGNORECASE,
)


def strip_title_v2(title: str) -> str:
    cleaned = _TITLE_V2_RE.sub("", title).strip()
    return cleaned if cleaned else title


def strip_note_v2(note: str) -> str:
    parts: list[str] = []
    last = 0
    for m in _URL_SPAN_RE.finditer(note):
        parts.append(_NOTE_V2_RE.sub("", note[last:m.start()]))
        parts.append(m.group(0))
        last = m.end()
    parts.append(_NOTE_V2_RE.sub("", note[last:]))
    return "".join(parts)


def upload_title_for(item: ModEntry, *, strip_numbers: bool = False, strip_v2: bool = False) -> str:
    raw = _normalize_single_line(item.title)
    if strip_numbers:
        raw = strip_title_index(raw)
    if strip_v2:
        raw = strip_title_v2(raw)
    return raw


def description_for(item: ModEntry, *, strip_numbers: bool = False, strip_v2: bool = False) -> str:
    title = upload_title_for(item, strip_numbers=strip_numbers, strip_v2=strip_v2)
    core = (
        f"Darkest Dungeon MOD: {title}\n\n"
        "私人 MOD 收藏与备份，原始作品和素材的权利归原作者所有。\n"
        "如需公开转载，请先确认原作者许可。"
    )
    note = _clean_text(item.note.strip())
    if strip_numbers and note:
        note = strip_note_indices(note)
    if strip_v2 and note:
        note = strip_note_v2(note)
    note = note.strip()
    return f"{core}\n\n{note}" if note else core


def _is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def compress_preview(preview: Path) -> tuple[int, bool]:
    size = preview.stat().st_size
    if size < MAX_PREVIEW_BYTES:
        return size, False
    try:
        from PIL import Image
        with Image.open(preview) as img:
            img.load()
            img.thumbnail((512, 512), Image.Resampling.LANCZOS)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            img.save(preview, format="PNG", optimize=True, compress_level=9)
            if preview.stat().st_size >= MAX_PREVIEW_BYTES:
                # Only transform the staged copy, never the user's source image.
                palette = img.convert("RGBA").quantize(
                    colors=256, method=Image.Quantize.FASTOCTREE
                )
                palette.save(preview, format="PNG", optimize=True)
    except Exception as exc:
        raise RuntimeError(f"自动压缩预览图失败：{exc}") from exc
    after = preview.stat().st_size
    if after >= MAX_PREVIEW_BYTES:
        raise RuntimeError(f"压缩后预览图仍超过限制：{after:,} 字节")
    return after, True


def prepare_project(item: ModEntry, workspace: Path, announce: Callable[[str], None], *, strip_numbers: bool = False, strip_v2: bool = False) -> Path:
    source = item.source.resolve()
    folder = project_dir(workspace, source)
    payload = folder / "payload"
    staging = folder / "payload.partial"
    rollback = folder / "payload.previous"
    xml_path = folder / "upload.xml"

    if _is_inside(folder, source) or _is_inside(source, folder):
        raise RuntimeError("归档位置与源 MOD 目录重叠；请将归档目录设在其他位置。")
    if not (source / "preview_icon.png").is_file():
        raise RuntimeError("源目录缺少 preview_icon.png")
    own_id = read_own_id(xml_path)
    # Validate user-editable metadata before touching a prepared payload.
    # A bad title must not replace a previously verified staging directory.
    normalized_title = upload_title_for(item, strip_numbers=strip_numbers, strip_v2=strip_v2)
    if not normalized_title:
        raise RuntimeError("上传标题不能为空。")
    normalized_description = description_for(item, strip_numbers=strip_numbers, strip_v2=strip_v2)
    if len(normalized_description) > 12000:
        raise RuntimeError("描述文字过长（超过 12000 字符）。")

    folder.mkdir(parents=True, exist_ok=True)
    if staging.exists():
        shutil.rmtree(staging)
    if rollback.exists():
        shutil.rmtree(rollback)

    def ignore_root(current: str, names: list[str]) -> list[str]:
        if Path(current).resolve() != source:
            return []
        excluded = [name for name in names if name.casefold() in IGNORE_ROOT]
        # Some previously downloaded Workshop copies contain an extra `data`
        # directory with uploader-generated metadata only. Drop that directory,
        # but NEVER drop a `data` directory containing actual MOD resources.
        for name in names:
            if name.casefold() != "data":
                continue
            subdir = source / name
            if subdir.is_dir():
                children = list(subdir.iterdir())
                if children and all(
                    child.is_file() and child.name.casefold() in IGNORE_ROOT.union({"preview_icon.png"})
                    for child in children
                ):
                    excluded.append(name)
        return excluded

    shutil.copytree(source, staging, ignore=ignore_root)
    try:
        preview = staging / "preview_icon.png"
        img_size, optimized = compress_preview(preview)
        content = [p for p in staging.rglob("*") if p.is_file()]
        if len(content) <= 1:
            raise RuntimeError("MOD 中只有预览图，缺少实际资源文件。")
        announce(f"  {len(content)} 个文件 · 预览图 {img_size:,} 字节"
                 + (" · 已自动压缩（仅副本）" if optimized else ""))

        if payload.exists():
            payload.replace(rollback)
        staging.replace(payload)
        if rollback.exists():
            shutil.rmtree(rollback)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if rollback.exists() and not payload.exists():
            rollback.replace(payload)
        raise

    root = ET.Element("project")
    fields = {
        "PreviewIconFile": "preview_icon.png",
        "ItemDescriptionShort": "Private Darkest Dungeon MOD backup",
        "ModDataPath": payload.as_posix() + "/",
        "Title": normalized_title,
        "Language": "english",
        "UpdateDetails": "Private archive upload / update",
        "Visibility": "private",
        "UploadMode": "direct_upload",
        "VersionMajor": "0",
        "VersionMinor": "0",
        "TargetBuild": "0",
        "ItemDescription": normalized_description,
    }
    if not fields["Title"]:
        raise RuntimeError("上传标题不能为空。")
    for tag, text in fields.items():
        ET.SubElement(root, tag).text = text
    valid_tags = normalize_tags(item.tags)
    if valid_tags:
        tags_el = ET.SubElement(root, "Tags")
        for t in valid_tags:
            ET.SubElement(tags_el, "Tags").text = t
    if own_id:
        ET.SubElement(root, "PublishedFileId").text = own_id
    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")
    if xml_path.exists():
        shutil.copy2(xml_path, folder / "upload.xml.backup")
    pending_xml = folder / "upload.xml.tmp"
    tree.write(pending_xml, encoding="utf-8", xml_declaration=True)
    pending_xml.replace(xml_path)
    save_draft(workspace, item)
    return xml_path



# ---- Post-upload cache lifecycle ------------------------------------------
# The `payload` directory can be much larger than the project metadata.
# A verified successful upload needs its XML, ID, draft, status and diagnostics
# for future updates, but not the local payload copy: prepare_project() will
# reconstruct that copy from the original source on the next update.
# Never automatically prune a prepared-only or UNCONFIRMED project.

@dataclass
class CacheCleanupReport:
    projects_cleaned: int = 0
    directories_removed: int = 0
    bytes_freed: int = 0
    projects_skipped: int = 0
    errors: list[str] = field(default_factory=list)


def human_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:,.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{int(size)} B"


def _directory_bytes(directory: Path) -> int:
    total = 0
    # Explicitly refuse links; no need to follow links outside the workspace.
    for root, dirs, files in os.walk(directory, followlinks=False):
        if Path(root).is_symlink():
            raise RuntimeError(f"缓存目录包含符号链接：{root}")
        for name in dirs + files:
            item = Path(root) / name
            if item.is_symlink():
                raise RuntimeError(f"缓存目录包含符号链接：{item}")
        for name in files:
            item = Path(root) / name
            total += item.stat().st_size
    return total


def cleanup_successful_project(
    source: Path, workspace: Path,
    announce: Callable[[str], None] | None = None,
) -> tuple[int, int]:
    """Return (number of deleted cache folders, bytes reclaimed).

    Only the three *exact* generated payload folders can be deleted, and only
    when status.json explicitly confirms SUCCESS for the ID in upload.xml.
    Project metadata, existing Steam IDs and original MODs are never removed.
    """
    folder = project_dir(workspace, source)
    if not folder.is_dir() or folder.is_symlink():
        return (0, 0)
    state = _read_json(folder / "status.json")
    if state.get("status") != "SUCCESS":
        return (0, 0)
    xml_path = folder / "upload.xml"
    own_id = read_own_id(xml_path)
    if not own_id or own_id != str(state.get("workshop_id", "")):
        return (0, 0)
    # A manually repointed ModDataPath must not cause us to touch user files.
    try:
        xml_root = ET.parse(xml_path).getroot()
        mod_data = (xml_root.findtext("ModDataPath") or "").strip()
        if not mod_data or Path(mod_data).resolve() != (folder / "payload").resolve():
            return (0, 0)
    except (OSError, ET.ParseError):
        return (0, 0)
    if _is_inside(folder, source) or _is_inside(source, folder):
        raise RuntimeError("源目录与工作空间重叠，拒绝回收")

    names = ("payload", "payload.partial", "payload.previous")
    candidates = []
    total_bytes = 0
    # Validate the *entire* deletion set before deleting anything.
    for name in names:
        path = folder / name
        if path.is_symlink():
            raise RuntimeError(f"缓存路径是符号链接，拒绝清理：{path}")
        if path.exists():
            if not path.is_dir() or path.parent.resolve() != folder.resolve():
                raise RuntimeError(f"缓存路径异常，拒绝清理：{path}")
            total_bytes += _directory_bytes(path)
            candidates.append(path)
    if not candidates:
        return (0, 0)
    for path in candidates:
        shutil.rmtree(path)
    if announce:
        announce(f"  已回收上传副本：{human_bytes(total_bytes)}（保留工坊 ID、XML 和日志）")
    return (len(candidates), total_bytes)


def cleanup_successful_workspace(
    workspace: Path, announce: Callable[[str], None] | None = None,
) -> CacheCleanupReport:
    """Clean historical SUCCESS payloads, without touching other projects."""
    result = CacheCleanupReport()
    projects_dir = workspace.resolve() / "projects"
    if not projects_dir.is_dir() or projects_dir.is_symlink():
        return result
    for folder in sorted(projects_dir.iterdir(), key=lambda p: p.name.casefold()):
        if not folder.is_dir() or folder.is_symlink():
            continue
        draft = _read_json(folder / "draft.json")
        source_text = draft.get("source")
        if not isinstance(source_text, str) or not source_text:
            result.projects_skipped += 1
            continue
        source = Path(source_text)
        if not source.is_absolute() or project_dir(workspace, source).resolve() != folder.resolve():
            result.projects_skipped += 1
            continue
        try:
            count, size = cleanup_successful_project(source, workspace)
        except (OSError, RuntimeError, ValueError) as exc:
            result.errors.append(f"{folder.name}: {exc}")
            continue
        if count:
            result.projects_cleaned += 1
            result.directories_removed += count
            result.bytes_freed += size
            if announce:
                announce(f"  {source.name}: 回收 {human_bytes(size)}")
        else:
            result.projects_skipped += 1
    return result

def _steam_log_path() -> Path:
    steam_root = detect_steam_root()
    if steam_root is not None:
        return steam_root / "logs" / "workshop_log.txt"
    root = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    return root / "Steam" / "logs" / "workshop_log.txt"


def read_log_delta(log_path: Path, previous_size: int) -> str:
    if not log_path.is_file():
        return ""
    now = log_path.stat().st_size
    offset = previous_size if now >= previous_size else 0
    with log_path.open("rb") as stream:
        stream.seek(offset)
        return stream.read()[-24000:].decode("utf-8", errors="replace")


def upload_project(
    item: ModEntry,
    workspace: Path,
    uploader: Path,
    announce: Callable[[str], None],
) -> tuple[bool, str]:
    folder = project_dir(workspace, item.source)
    xml_path = folder / "upload.xml"
    state_path = folder / "status.json"
    steam_log = _steam_log_path()
    before = steam_log.stat().st_size if steam_log.exists() else 0
    announce("  正在调用 Steam 工坊上传器……")
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    try:
        result = subprocess.run(
            [str(uploader), str(xml_path)],
            input=b"\r\n", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=900, check=False, **kwargs,
        )
        raw = result.stdout or b""
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or b""
        if isinstance(raw, str):
            raw = raw.encode("utf-8", errors="replace")
        timed_out = True
    except OSError as exc:
        raw = str(exc).encode("utf-8", errors="replace")
        timed_out = False

    (folder / "uploader.log").write_bytes(raw)
    try:
        text = raw.decode("mbcs" if os.name == "nt" else "utf-8", errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    diagnostic = read_log_delta(steam_log, before)
    (folder / "steam_workshop_diagnostic.log").write_text(diagnostic, encoding="utf-8")

    sentinel = _sanitize_sentinel_id(xml_path)
    new_id = read_own_id(xml_path)
    return_code = result.returncode if "result" in locals() else None
    success = (
        bool(new_id)
        and not timed_out
        and return_code == 0
        and "Submitted." in text
        and "Unhandled error" not in text
    )
    now = datetime.now().isoformat(timespec="seconds")
    write_json(state_path, {
        "status": "SUCCESS" if success else "UNCONFIRMED",
        "workshop_id": new_id,
        "updated_at": now,
        "uploader_return_code": return_code,
    })
    for line in text.splitlines()[-12:]:
        announce("  " + line)
    if diagnostic and not success:
        interesting = [line for line in diagnostic.splitlines() if any(
            term in line.casefold() for term in
            ("error", "failed", "limit exceeded", "denied", "file not found", "workshop item"))]
        if interesting:
            announce("  Steam 日志中的最新诊断：")
            for line in interesting[-8:]:
                announce("  " + line)
            joined = "\n".join(interesting).casefold()
            if "access denied" in joined and "create new workshop item" in joined:
                announce("  💡 诊断提示：Steam 拒绝新建条目 (Access Denied)。若刚连续上传百余个 MOD，通常是触发了 Steam 工坊创建配额冷却（冷却后重试或重启 Steam 客户端即可）。")
            elif "limit exceeded" in joined:
                announce("  💡 诊断提示：预览图或单项文件超出 Steam 大小限制。")
            elif "file not found" in joined:
                announce("  💡 诊断提示：上传器未找到资析或预览图文件，请检查源 MOD 目录完整性。")
    if success:
        # The download was submitted and the ID/status is already persisted.
        # Cleanup errors must NOT turn a successful Steam submission into a
        # failed/unknown upload: keep the payload and report the issue instead.
        try:
            cleanup_successful_project(item.source, workspace, announce)
        except (OSError, RuntimeError) as exc:
            announce(f"  ⚠ 已成功上传，但回收副本失败：{exc}（可稍后手动清理）")
    if sentinel:
        announce(f"  ⚠ 上传器写入了 Steam 无效占位 ID（{sentinel}），未创建条目，已自动清理占位标记。")
    if timed_out:
        announce("  上传器执行超时；不能判断是否已成功创建项目，请先检查日志。")
    elif return_code is None:
        announce("  无法启动上传器或取得退出状态；请检查工作目录与权限。")
    elif return_code != 0:
        announce(f"  上传器返回非零退出代码 {return_code}，本次不判定为成功。")
    return success, new_id
