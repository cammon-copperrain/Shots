"""Builds the Seedance prompt + fal request payload from shots. No AI involved:
it assembles the shot/scene/asset text you (or Claude Code) already wrote.

Local files are written as "local:<project-relative path>"; they are uploaded
to fal storage and swapped for URLs only when the job is sent.
"""

import math

from . import store

MAX_IMAGES = 30
MAX_VIDEOS = 10
MAX_REF_SECONDS = 30.2


def _ordered(data, shot_ids):
    wanted = set(shot_ids)
    return [s for s in data["shots"] if s["id"] in wanted]


def _sentence(text):
    text = text.strip()
    return text if not text or text[-1] in ".!?" else text + "."


def shot_section(data, shot, index, total):
    if shot.get("prompt_override", "").strip():
        body = shot["prompt_override"].strip()
    else:
        parts = []
        if shot.get("description"):
            parts.append(shot["description"].strip())
        if shot.get("camera"):
            parts.append(f"Camera: {shot['camera'].strip()}")
        if shot.get("action"):
            parts.append(f"Action: {shot['action'].strip()}")
        notes = [n["text"].strip() for n in shot["notes"] if n.get("to_prompt") and n["text"].strip()]
        if notes:
            parts.append("Notes: " + " ".join(notes))
        if shot.get("prompt_extra"):
            parts.append(shot["prompt_extra"].strip())
        body = " ".join(_sentence(p) for p in parts)
    label = f"Shot {index} of {total}" if total > 1 else "Shot"
    return f"{label} ({shot['id']}, ~{float(shot.get('duration') or 0):g}s): {body}"


def build_request(data, shot_ids, mode="clips", animatic=None):
    """mode: 'clips' = each shot's latest previs as its own @Video,
    'animatic' = one combined previs video, 'none' = no video reference."""
    shots = _ordered(data, shot_ids)
    if not shots:
        raise store.StoreError("no shots selected")
    warnings = []
    scenes = {s["id"]: s for s in data["scenes"]}

    char_ids, env_ids, scene_ids = [], [], []
    for shot in shots:
        sc = scenes.get(shot.get("scene_id"))
        if sc and sc["id"] not in scene_ids:
            scene_ids.append(sc["id"])
        for cid in shot.get("character_ids", []) + (sc or {}).get("character_ids", []):
            if cid not in char_ids:
                char_ids.append(cid)
        for eid in shot.get("environment_ids", []) + (sc or {}).get("environment_ids", []):
            if eid not in env_ids:
                env_ids.append(eid)

    images, ref_lines = [], []
    for kind, ids, label in (("characters", char_ids, "character sheet"),
                             ("environments", env_ids, "environment / set reference")):
        for aid in ids:
            try:
                asset = store.find(data, kind, aid)
            except store.StoreError:
                continue
            tags = []
            for img in asset["images"]:
                images.append(img)
                tags.append(f"@Image{len(images)}")
            desc = f" ({asset['description'].strip()})" if asset.get("description") else ""
            if tags:
                ref_lines.append(f"{' '.join(tags)}: {asset['name']}, {label}{desc}.")
            elif asset.get("description"):
                ref_lines.append(f"{asset['name']}: {asset['description'].strip()}.")

    videos = []
    if mode == "clips":
        for i, shot in enumerate(shots, 1):
            v = store.latest_version(shot, "previs")
            if v:
                videos.append(v["file"])
                ref_lines.append(f"@Video{len(videos)}: previs for shot {i} ({shot['id']}). "
                                 "Match its blocking, framing, camera move and timing.")
            else:
                warnings.append(f"{shot['id']} has no previs yet")
    elif mode == "animatic":
        if animatic:
            videos.append(animatic)
            ref_lines.append("@Video1: previs animatic of the whole sequence. Match its shot order, "
                             "blocking, framing, camera moves and cut timing.")
        else:
            warnings.append("export the animatic first")

    total = sum(float(s.get("duration") or 0) for s in shots)
    if len(images) > MAX_IMAGES:
        warnings.append(f"{len(images)} images; Seedance reference limit is {MAX_IMAGES}")
    if len(videos) > MAX_VIDEOS:
        warnings.append(f"{len(videos)} videos; Seedance reference limit is {MAX_VIDEOS}")
    if mode == "animatic" and total > MAX_REF_SECONDS:
        warnings.append(f"planned length {total:g}s; a video reference must be <= {MAX_REF_SECONDS}s")

    lines = []
    style = data.get("style", {})
    if style.get("look"):
        lines.append(f"Look: {_sentence(style['look'])}")
    if style.get("consistency"):
        lines.append(f"Keep consistent: {_sentence(style['consistency'])}")
    for sid in scene_ids:
        sc = scenes[sid]
        if sc.get("description"):
            lines.append(f"Scene {sc.get('title') or sid}: {_sentence(sc['description'])}")
    if ref_lines:
        lines.append("References: " + " ".join(ref_lines))
    if len(shots) > 1:
        lines.append(f"Multi-shot sequence, {len(shots)} shots in order, hard cuts between shots.")
    for i, shot in enumerate(shots, 1):
        lines.append(shot_section(data, shot, i, len(shots)))

    payload = {"prompt": "\n".join(lines)}
    if images:
        payload["image_urls"] = ["local:" + p for p in images]
    if videos:
        payload["video_urls"] = ["local:" + p for p in videos]
    if total:
        payload["duration"] = str(math.ceil(total))
    payload.update(store.load_config().get("fal_defaults", {}))
    return {"payload": payload, "warnings": warnings, "shot_ids": [s["id"] for s in shots],
            "planned_seconds": total}
