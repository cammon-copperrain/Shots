"""Background work: fal.ai generations, Blender previs renders, animatic export.
Each job is recorded in project.json["jobs"] so its state survives restarts."""

import os
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
import urllib.request
from pathlib import Path

from . import store

RENDER_SCRIPT = store.ROOT / "tools" / "blender_render_shot.py"


def _new_job(name, kind, shot_ids, **extra):
    job = {"id": store.short_id("job"), "kind": kind, "shot_ids": shot_ids,
           "status": "queued", "created": store.now(), "finished": "", "error": "", **extra}
    store.mutate(name, lambda d: d["jobs"].insert(0, job))
    return job


def _update(name, job_id, **fields):
    def fn(d):
        for j in d["jobs"]:
            if j["id"] == job_id:
                j.update(fields)
    store.mutate(name, fn)


def _run(name, job_id, work):
    def target():
        try:
            work()
            _update(name, job_id, status="done", finished=store.now())
        except Exception as e:  # recorded on the job so the UI can show it
            traceback.print_exc()
            _update(name, job_id, status="error", error=f"{type(e).__name__}: {e}",
                    finished=store.now())
    threading.Thread(target=target, daemon=True).start()


# ---------- fal ----------

def _resolve_locals(name, value, upload, cache):
    if isinstance(value, str) and value.startswith("local:"):
        rel = value[len("local:"):]
        if rel not in cache:
            cache[rel] = upload(str(store.safe_path(name, rel)))
        return cache[rel]
    if isinstance(value, list):
        return [_resolve_locals(name, v, upload, cache) for v in value]
    if isinstance(value, dict):
        return {k: _resolve_locals(name, v, upload, cache) for k, v in value.items()}
    return value


def _find_video_url(result):
    if isinstance(result, dict):
        video = result.get("video")
        if isinstance(video, dict) and video.get("url"):
            return video["url"]
        for v in result.values():
            url = _find_video_url(v)
            if url:
                return url
    elif isinstance(result, list):
        for v in result:
            url = _find_video_url(v)
            if url:
                return url
    elif isinstance(result, str) and result.startswith("http") and \
            result.split("?")[0].lower().endswith((".mp4", ".mov", ".webm")):
        return result
    return None


def start_fal(name, shot_ids, endpoint, payload):
    cfg = store.load_config()
    if not cfg["fal_key"]:
        raise store.StoreError("no fal key: add fal_key to config.json or set FAL_KEY")
    job = _new_job(name, "fal", shot_ids, endpoint=endpoint, request_id="", result_url="")

    def work():
        import fal_client
        os.environ["FAL_KEY"] = cfg["fal_key"]
        _update(name, job["id"], status="uploading")
        args = _resolve_locals(name, payload, fal_client.upload_file, {})
        handle = fal_client.submit(endpoint, arguments=args)
        _update(name, job["id"], status="generating", request_id=handle.request_id,
                sent_payload=args)
        result = handle.get()
        url = _find_video_url(result)
        if not url:
            raise store.StoreError(f"no video in fal result: {str(result)[:500]}")
        _update(name, job["id"], status="downloading", result_url=url)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "seedance.mp4"
            urllib.request.urlretrieve(url, dest)
            data = store.load(name)
            shots = [s for s in data["shots"] if s["id"] in shot_ids]
            offset, stored = 0.0, None
            for shot in shots:
                dur = float(shot.get("duration") or 0)
                meta = {"job": job["id"], "endpoint": endpoint, "url": url}
                if len(shots) > 1:
                    meta.update(span=[s["id"] for s in shots], start=offset, end=offset + dur)
                if stored is None:  # one file on disk, the other shots point at it
                    stored = store.register_version(name, shot["id"], dest, "seedance", meta)["file"]
                else:
                    store.add_version_ref(name, shot["id"], stored, "seedance", meta)
                offset += dur

    _run(name, job["id"], work)
    return job


# ---------- Blender previs ----------

def start_render(name, shot_id):
    cfg = store.load_config()
    blender = cfg["blender_path"]
    if not (Path(blender).exists() or shutil.which(blender)):
        raise store.StoreError(f"Blender not found at {blender}; set blender_path in config.json")
    data = store.load(name)
    shot = store.find(data, "shots", shot_id)
    b = shot.get("blender") or {}
    if not b.get("file"):
        raise store.StoreError(f"{shot_id} has no Blender file set")
    blend = store.safe_path(name, b["file"])
    _, rel = store.next_version_path(data, shot_id, "previs", ".mp4")
    out = store.safe_path(name, rel)
    out.parent.mkdir(parents=True, exist_ok=True)
    job = _new_job(name, "render", [shot_id])

    def work():
        _update(name, job["id"], status="rendering")
        cmd = [blender, "-b", str(blend), "-P", str(RENDER_SCRIPT), "--",
               "--out", str(out), "--start", str(b.get("start", 1)), "--end", str(b.get("end", 96))]
        if b.get("camera"):
            cmd += ["--camera", b["camera"]]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not out.exists():
            raise store.StoreError("Blender failed:\n" + (proc.stdout + proc.stderr)[-2000:])
        store.register_version(name, shot_id, out, "previs", {"job": job["id"], "source": "app"})

    _run(name, job["id"], work)
    return job


# ---------- animatic ----------

def export_animatic(name, shot_ids):
    """Concatenate each shot's latest previs into animatics/anim_<time>.mp4 (blocking call)."""
    cfg = store.load_config()
    ffmpeg = shutil.which(cfg["ffmpeg_path"]) or (cfg["ffmpeg_path"] if Path(cfg["ffmpeg_path"]).exists() else None)
    if not ffmpeg:
        raise store.StoreError("ffmpeg not found; install it (brew install ffmpeg) or set ffmpeg_path")
    data = store.load(name)
    shots = [s for s in data["shots"] if s["id"] in set(shot_ids)]
    clips = []
    for s in shots:
        v = store.latest_version(s, "previs")
        if not v:
            raise store.StoreError(f"{s['id']} has no previs to put in the animatic")
        clips.append(store.safe_path(name, v["file"]))
    rel = f"animatics/anim_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
    out = store.safe_path(name, rel)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for c in clips:
            f.write("file '" + str(c).replace("'", "'\\''") + "'\n")
        listfile = f.name
    try:
        proc = subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", listfile,
                               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out)],
                              capture_output=True, text=True)
    finally:
        os.unlink(listfile)
    if proc.returncode != 0:
        raise store.StoreError("ffmpeg failed:\n" + proc.stderr[-1500:])
    return rel
