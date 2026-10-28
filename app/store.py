"""Project storage shared by the web app and the Claude Code CLI (shots_cli.py).

Every project is a folder under `projects_dir` holding a `project.json` plus
its media. Writes are atomic and always read-modify-write from disk, so the
app and a Claude Code session can both edit the same project.
Standard library only, so the CLI runs without the app's dependencies.
"""

import json
import os
import re
import secrets
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT_FILE = "project.json"
COLLECTIONS = ("scenes", "shots", "characters", "environments")
NOTE_TYPES = ("framing", "blocking", "timing", "camera", "acting", "general")
PROMPT_NOTE_TYPES = ("camera", "acting")  # default "carry into prompt" for these
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

DEFAULT_CONFIG = {
    "projects_dir": "~/Library/CloudStorage/Dropbox/Shots Projects",
    "fal_key": "",
    "fal_endpoint": "bytedance/seedance-2.5/reference-to-video",
    "fal_defaults": {"resolution": "480p"},
    "blender_path": "/Applications/Blender.app/Contents/MacOS/Blender",
    "ffmpeg_path": "ffmpeg",
    "port": 8765,
}

_lock = threading.RLock()


class StoreError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    path = ROOT / "config.json"
    if path.exists():
        cfg.update(json.loads(path.read_text()))
    cfg["projects_dir"] = os.path.expanduser(cfg["projects_dir"])
    key = cfg.get("fal_key") or ""
    cfg["fal_key"] = "" if key.startswith("PASTE") else key or os.environ.get("FAL_KEY", "")
    return cfg


def projects_dir():
    d = Path(load_config()["projects_dir"])
    d.mkdir(parents=True, exist_ok=True)
    return d


def slugify(text):
    slug = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return slug or "Untitled"


def project_dir(name):
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise StoreError(f"bad project name: {name!r}")
    d = projects_dir() / name
    if not (d / PROJECT_FILE).exists():
        raise StoreError(f"no such project: {name}")
    return d


def safe_path(name, rel):
    """Resolve a project-relative path, refusing anything outside the project."""
    base = project_dir(name).resolve()
    p = (base / rel).resolve()
    if base != p and base not in p.parents:
        raise StoreError(f"path outside project: {rel}")
    return p


def list_projects():
    out = []
    for d in sorted(projects_dir().iterdir()):
        f = d / PROJECT_FILE
        if d.is_dir() and f.exists():
            try:
                data = json.loads(f.read_text())
            except ValueError:
                data = {}
            out.append({"name": d.name, "title": data.get("title", d.name),
                        "updated": f.stat().st_mtime, "shots": len(data.get("shots", []))})
    out.sort(key=lambda p: -p["updated"])
    return out


def empty_project(title):
    return {
        "schema": 1, "title": title, "created": now(),
        "outline": "", "script": "",
        "style": {"look": "", "consistency": ""},
        "scenes": [], "shots": [], "characters": [], "environments": [], "jobs": [],
    }


def create_project(title):
    with _lock:
        base = slugify(title)
        name, i = base, 2
        while (projects_dir() / name).exists():
            name, i = f"{base}_{i}", i + 1
        d = projects_dir() / name
        for sub in ("shots", "assets/characters", "assets/environments", "blender", "animatics"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        _write(d, empty_project(title))
        return name


def _write(d, data):
    data["updated"] = now()
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".project.", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, d / PROJECT_FILE)


def load(name):
    return json.loads((project_dir(name) / PROJECT_FILE).read_text())


def mtime(name):
    return (project_dir(name) / PROJECT_FILE).stat().st_mtime


def mutate(name, fn):
    """Load, apply fn(data) -> result, save. Returns (data, result)."""
    with _lock:
        d = project_dir(name)
        data = json.loads((d / PROJECT_FILE).read_text())
        result = fn(data)
        _write(d, data)
        return data, result


# ---------- lookups ----------

def find(data, collection, item_id):
    for item in data.get(collection, []):
        if item["id"] == item_id:
            return item
    raise StoreError(f"no {collection[:-1]} {item_id}")


def short_id(prefix):
    return f"{prefix}_{secrets.token_hex(3)}"


# ---------- shots & scenes ----------

def _shot_num(sid):
    m = re.fullmatch(r"sh(\d+)([A-Z]*)", sid or "")
    return int(m.group(1)) if m else None


def shot_id_between(shots, prev_id, next_id):
    """sh010 / sh020 -> sh015; no room -> sh010A. Append -> next multiple of 10."""
    existing = {s["id"] for s in shots}
    p = _shot_num(prev_id) or 0
    n = _shot_num(next_id)
    if n is None:
        cand = (max([_shot_num(s["id"]) or 0 for s in shots] + [p]) // 10 + 1) * 10
    else:
        cand = (p + n) // 2 if n - p > 1 else None
    if cand is not None and f"sh{cand:03d}" not in existing:
        return f"sh{cand:03d}"
    root = prev_id or "sh000"
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if f"{root}{letter}" not in existing:
            return f"{root}{letter}"
    raise StoreError("no free shot id")


def new_shot(fields=None):
    shot = {
        "id": "", "scene_id": "", "title": "", "description": "",
        "camera": "", "action": "", "duration": 4,
        "character_ids": [], "environment_ids": [],
        "prompt_extra": "", "prompt_override": "",
        "blender": {"file": "", "camera": "", "start": 1, "end": 96},
        "notes": [], "versions": [], "current": "",
    }
    shot.update(fields or {})
    return shot


def insert_shot(data, after_id=None, fields=None):
    shots = data["shots"]
    if after_id:
        idx = next(i for i, s in enumerate(shots) if s["id"] == after_id) + 1
    elif after_id == "":  # explicit "insert at start"
        idx = 0
    else:
        idx = len(shots)
    prev_id = shots[idx - 1]["id"] if idx > 0 else None
    next_id = shots[idx]["id"] if idx < len(shots) else None
    fields = dict(fields or {})
    if not fields.get("scene_id"):
        neighbour = shots[idx - 1] if idx > 0 else (shots[idx] if shots else None)
        fields["scene_id"] = neighbour["scene_id"] if neighbour else (
            data["scenes"][0]["id"] if data["scenes"] else "")
    shot = new_shot(fields)
    shot["id"] = fields.get("id") or shot_id_between(shots, prev_id, next_id)
    if shot["blender"].get("file") and not shot["blender"].get("camera"):
        shot["blender"]["camera"] = f"CAM_{shot['id']}"
    shots.insert(idx, shot)
    return shot


def new_scene(data, fields=None):
    nums = [int(m.group(1)) for s in data["scenes"] if (m := re.fullmatch(r"sc(\d+)", s["id"]))]
    scene = {"id": f"sc{(max(nums + [0]) // 10 + 1) * 10:03d}", "title": "", "description": "",
             "character_ids": [], "environment_ids": []}
    scene.update(fields or {})
    data["scenes"].append(scene)
    return scene


def new_asset(data, kind, fields=None):
    asset = {"id": short_id("ch" if kind == "characters" else "env"),
             "name": "", "description": "", "images": []}
    asset.update(fields or {})
    data[kind].append(asset)
    return asset


def add_note(shot, text, note_type="general", to_prompt=None):
    if note_type not in NOTE_TYPES:
        note_type = "general"
    note = {"id": short_id("n"), "type": note_type, "text": text, "status": "pending",
            "to_prompt": note_type in PROMPT_NOTE_TYPES if to_prompt is None else bool(to_prompt),
            "created": now(), "resolved": "", "reply": ""}
    shot["notes"].append(note)
    return note


# ---------- versions ----------

def next_version_path(data, shot_id, kind, ext):
    shot = find(data, "shots", shot_id)
    n = max([v["v"] for v in shot["versions"]] + [0]) + 1
    ext = ext if ext.startswith(".") else "." + ext
    return n, f"shots/{shot_id}/v{n:03d}_{kind}{ext}"


def register_version(name, shot_id, src, kind, meta=None, move=False):
    """Copy/move src into the shot's folder as the next version and make it current."""
    src = Path(src).resolve()
    if not src.exists():
        raise StoreError(f"missing file: {src}")
    base = project_dir(name).resolve()

    def fn(data):
        shot = find(data, "shots", shot_id)
        try:
            rel_existing = src.relative_to(base).as_posix()
        except ValueError:
            rel_existing = None
        if rel_existing and rel_existing.startswith(f"shots/{shot_id}/") and \
                not any(v["file"] == rel_existing for v in shot["versions"]):
            # already rendered into place (e.g. via next-version-path)
            m = re.match(r"v(\d+)_", Path(rel_existing).name)
            n = int(m.group(1)) if m else max([v["v"] for v in shot["versions"]] + [0]) + 1
            rel = rel_existing
        else:
            n, rel = next_version_path(data, shot_id, kind, src.suffix)
            dest = base / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            (shutil.move if move else shutil.copy2)(str(src), str(dest))
        version = {"v": n, "kind": kind, "file": rel, "created": now(), "meta": meta or {}}
        shot["versions"].append(version)
        shot["current"] = rel
        return version

    return mutate(name, fn)[1]


def add_version_ref(name, shot_id, rel, kind, meta=None):
    """Point a shot at a file that already lives in the project (e.g. a multi-shot clip)."""
    safe_path(name, rel)

    def fn(data):
        shot = find(data, "shots", shot_id)
        n = max([v["v"] for v in shot["versions"]] + [0]) + 1
        version = {"v": n, "kind": kind, "file": rel, "created": now(), "meta": meta or {}}
        shot["versions"].append(version)
        shot["current"] = rel
        return version

    return mutate(name, fn)[1]


def latest_version(shot, kind):
    vs = [v for v in shot["versions"] if v["kind"] == kind]
    return vs[-1] if vs else None
