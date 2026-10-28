"""Shots local server. Run via Shots.command, or:
    python -m uvicorn app.server:app --port 8765
"""

import shutil
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import jobs, prompt, store

app = FastAPI(title="Shots")
STATIC = Path(__file__).parent / "static"

EDITABLE = {
    "scenes": {"title", "description", "character_ids", "environment_ids"},
    "shots": {"scene_id", "title", "description", "camera", "action", "duration",
              "character_ids", "environment_ids", "prompt_extra", "prompt_override",
              "blender", "current"},
    "characters": {"name", "description"},
    "environments": {"name", "description"},
}
PROJECT_FIELDS = {"title", "outline", "script", "style"}


@app.exception_handler(store.StoreError)
async def store_error(_: Request, exc: store.StoreError):
    return JSONResponse({"error": str(exc)}, status_code=400)


def _collection(c):
    if c not in store.COLLECTIONS:
        raise HTTPException(404, f"unknown collection {c}")
    return c


# ---------- app / projects ----------

@app.get("/api/config")
def config():
    cfg = store.load_config()
    return {"projects_dir": cfg["projects_dir"], "fal_ready": bool(cfg["fal_key"]),
            "fal_endpoint": cfg["fal_endpoint"],
            "blender_found": Path(cfg["blender_path"]).exists() or bool(shutil.which(cfg["blender_path"])),
            "ffmpeg_found": bool(shutil.which(cfg["ffmpeg_path"]) or Path(cfg["ffmpeg_path"]).exists())}


@app.get("/api/projects")
def projects():
    return store.list_projects()


@app.post("/api/projects")
def create_project(body: dict = Body(...)):
    return {"name": store.create_project(body.get("title") or "Untitled")}


@app.get("/api/projects/{p}")
def get_project(p: str):
    data = store.load(p)
    data["_mtime"] = store.mtime(p)
    return data


@app.get("/api/projects/{p}/mtime")
def get_mtime(p: str):
    return {"mtime": store.mtime(p)}


@app.patch("/api/projects/{p}")
def patch_project(p: str, body: dict = Body(...)):
    def fn(d):
        for k, v in body.items():
            if k in PROJECT_FIELDS:
                d[k] = v
    store.mutate(p, fn)
    return {"ok": True}


# ---------- scenes / shots / assets ----------

@app.post("/api/projects/{p}/items/{c}")
def create_item(p: str, c: str, body: dict = Body(default={})):
    c = _collection(c)
    fields = {k: v for k, v in body.items() if k in EDITABLE[c]}

    def fn(d):
        if c == "shots":
            return store.insert_shot(d, body.get("after"), fields)
        if c == "scenes":
            return store.new_scene(d, fields)
        return store.new_asset(d, c, fields)
    return store.mutate(p, fn)[1]


@app.patch("/api/projects/{p}/items/{c}/{item_id}")
def patch_item(p: str, c: str, item_id: str, body: dict = Body(...)):
    c = _collection(c)

    def fn(d):
        item = store.find(d, c, item_id)
        for k, v in body.items():
            if k in EDITABLE[c]:
                item[k] = v
        return item
    return store.mutate(p, fn)[1]


@app.delete("/api/projects/{p}/items/{c}/{item_id}")
def delete_item(p: str, c: str, item_id: str):
    c = _collection(c)
    store.mutate(p, lambda d: d.__setitem__(c, [i for i in d[c] if i["id"] != item_id]))
    return {"ok": True}


@app.post("/api/projects/{p}/shots-order")
def reorder(p: str, body: dict = Body(...)):
    order = body["ids"]

    def fn(d):
        by_id = {s["id"]: s for s in d["shots"]}
        if set(order) != set(by_id):
            raise store.StoreError("order must list every shot exactly once")
        d["shots"] = [by_id[i] for i in order]
    store.mutate(p, fn)
    return {"ok": True}


# ---------- notes ----------

@app.post("/api/projects/{p}/shots/{sid}/notes")
def add_note(p: str, sid: str, body: dict = Body(...)):
    return store.mutate(p, lambda d: store.add_note(
        store.find(d, "shots", sid), body.get("text", ""), body.get("type", "general"),
        body.get("to_prompt")))[1]


@app.patch("/api/projects/{p}/shots/{sid}/notes/{nid}")
def patch_note(p: str, sid: str, nid: str, body: dict = Body(...)):
    def fn(d):
        note = next(n for n in store.find(d, "shots", sid)["notes"] if n["id"] == nid)
        for k in ("text", "type", "status", "to_prompt", "reply"):
            if k in body:
                note[k] = body[k]
        if body.get("status") == "done" and not note["resolved"]:
            note["resolved"] = store.now()
        if body.get("status") == "pending":
            note["resolved"] = ""
        return note
    return store.mutate(p, fn)[1]


@app.delete("/api/projects/{p}/shots/{sid}/notes/{nid}")
def delete_note(p: str, sid: str, nid: str):
    def fn(d):
        shot = store.find(d, "shots", sid)
        shot["notes"] = [n for n in shot["notes"] if n["id"] != nid]
    store.mutate(p, fn)
    return {"ok": True}


# ---------- uploads ----------

def _save_upload(p, rel_dir, upload: UploadFile):
    name = store.slugify(Path(upload.filename or "file").stem) + Path(upload.filename or "").suffix.lower()
    dest = store.safe_path(p, f"{rel_dir}/{name}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    stem, i = dest.stem, 2
    while dest.exists():
        dest = dest.with_name(f"{stem}_{i}{dest.suffix}")
        i += 1
    with dest.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return dest


@app.post("/api/projects/{p}/items/{c}/{aid}/images")
def add_asset_image(p: str, c: str, aid: str, file: UploadFile = File(...)):
    c = _collection(c)
    if c not in ("characters", "environments"):
        raise HTTPException(400, "images belong to characters or environments")
    dest = _save_upload(p, f"assets/{c}/{aid}", file)
    rel = dest.relative_to(store.project_dir(p).resolve()).as_posix()
    store.mutate(p, lambda d: store.find(d, c, aid)["images"].append(rel))
    return {"file": rel}


@app.delete("/api/projects/{p}/items/{c}/{aid}/images")
def remove_asset_image(p: str, c: str, aid: str, file: str):
    c = _collection(c)

    def fn(d):
        a = store.find(d, c, aid)
        a["images"] = [i for i in a["images"] if i != file]
    store.mutate(p, fn)
    return {"ok": True}


@app.post("/api/projects/{p}/shots/{sid}/versions")
def upload_version(p: str, sid: str, file: UploadFile = File(...), kind: str = Form("previs")):
    tmp = _save_upload(p, ".incoming", file)
    try:
        return store.register_version(p, sid, tmp, kind, {"source": "upload"}, move=True)
    finally:
        tmp.unlink(missing_ok=True)
        try:
            tmp.parent.rmdir()
        except OSError:
            pass


# ---------- prompt / fal / render / animatic ----------

@app.post("/api/projects/{p}/prompt")
def build_prompt(p: str, body: dict = Body(...)):
    out = prompt.build_request(store.load(p), body["shot_ids"], body.get("mode", "clips"),
                               body.get("animatic"))
    out["endpoint"] = store.load_config()["fal_endpoint"]
    return out


@app.post("/api/projects/{p}/animatic")
def animatic(p: str, body: dict = Body(...)):
    return {"file": jobs.export_animatic(p, body["shot_ids"])}


@app.post("/api/projects/{p}/fal")
def send_to_fal(p: str, body: dict = Body(...)):
    return jobs.start_fal(p, body["shot_ids"], body.get("endpoint") or store.load_config()["fal_endpoint"],
                          body["payload"])


@app.post("/api/projects/{p}/shots/{sid}/render")
def render(p: str, sid: str):
    return jobs.start_render(p, sid)


@app.delete("/api/projects/{p}/jobs")
def clear_jobs(p: str):
    store.mutate(p, lambda d: d.__setitem__("jobs", [j for j in d["jobs"]
                                                      if j["status"] not in ("done", "error")]))
    return {"ok": True}


# ---------- media + UI ----------

@app.get("/files/{p}/{rel:path}")
def files(p: str, rel: str):
    path = store.safe_path(p, rel)
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
