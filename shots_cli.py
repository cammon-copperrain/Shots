#!/usr/bin/env python3
"""Command-line access to Shots projects, for Claude Code (and you).

    python3 shots_cli.py projects
    python3 shots_cli.py show    <project>
    python3 shots_cli.py notes   <project> [shot]            # pending notes as JSON
    python3 shots_cli.py resolve <project> <shot> <note_id> [--reply "what changed"]
    python3 shots_cli.py next-path <project> <shot> [--kind previs] [--ext mp4]
    python3 shots_cli.py register  <project> <shot> <file> [--kind previs] [--move]
    python3 shots_cli.py add-scene <project> --title T [--description D]
    python3 shots_cli.py add-shot  <project> --scene sc010 [--after sh010] [--title ..]
          [--description ..] [--camera ..] [--action ..] [--duration 4]
          [--blend blender/sc010.blend] [--cam CAM_sh010] [--start 1] [--end 96]
    python3 shots_cli.py set <project> <shots|scenes|characters|environments> <id> field=value ...
    python3 shots_cli.py set-project <project> <title|outline|script|style.look|style.consistency>
          (--file path.md | --value "text")
    python3 shots_cli.py path <project>                        # absolute project folder

Uses only the standard library. Writes are atomic, so it is safe to run while the app is open.
"""

import argparse
import json
import sys

from app import store


def out(obj):
    print(json.dumps(obj, indent=2))


def cmd_projects(a):
    out(store.list_projects())


def cmd_path(a):
    print(store.project_dir(a.project))


def cmd_show(a):
    d = store.load(a.project)
    print(f"{d['title']}  ({store.project_dir(a.project)})")
    scenes = {s["id"]: s for s in d["scenes"]}
    for sc in d["scenes"]:
        print(f"\n{sc['id']} {sc['title']}: {sc['description'][:100]}")
        for s in [s for s in d["shots"] if s["scene_id"] == sc["id"]]:
            pend = sum(n["status"] == "pending" for n in s["notes"])
            b = s.get("blender") or {}
            print(f"  {s['id']:<8} {s['duration']:>4}s  v{len(s['versions'])}  "
                  f"{'notes:' + str(pend) if pend else '':<9} {b.get('file', '')}:{b.get('camera', '')}  "
                  f"{(s['title'] or s['description'])[:60]}")
    orphans = [s for s in d["shots"] if s["scene_id"] not in scenes]
    for s in orphans:
        print(f"  {s['id']:<8} (no scene) {(s['title'] or s['description'])[:60]}")
    print(f"\ncharacters: {', '.join(c['name'] or c['id'] for c in d['characters']) or '-'}")
    print(f"environments: {', '.join(e['name'] or e['id'] for e in d['environments']) or '-'}")


def cmd_notes(a):
    d = store.load(a.project)
    res = []
    for s in d["shots"]:
        if a.shot and s["id"] != a.shot:
            continue
        pend = [n for n in s["notes"] if n["status"] == "pending"]
        if pend:
            res.append({"shot": s["id"], "blender": s.get("blender"), "camera": s["camera"],
                        "action": s["action"], "duration": s["duration"], "notes": pend})
    out(res)


def cmd_resolve(a):
    def fn(d):
        note = next(n for n in store.find(d, "shots", a.shot)["notes"] if n["id"] == a.note_id)
        note.update(status="done", resolved=store.now(), reply=a.reply or note.get("reply", ""))
        return note
    out(store.mutate(a.project, fn)[1])


def cmd_next_path(a):
    _, rel = store.next_version_path(store.load(a.project), a.shot, a.kind, a.ext)
    p = store.safe_path(a.project, rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    print(p)


def cmd_register(a):
    out(store.register_version(a.project, a.shot, a.file, a.kind, {"source": "cli"}, move=a.move))


def cmd_add_scene(a):
    out(store.mutate(a.project, lambda d: store.new_scene(
        d, {"title": a.title, "description": a.description or ""}))[1])


def cmd_add_shot(a):
    fields = {"scene_id": a.scene}
    for k in ("title", "description", "camera", "action"):
        if getattr(a, k):
            fields[k] = getattr(a, k)
    if a.duration is not None:
        fields["duration"] = a.duration
    if a.id:
        fields["id"] = a.id
    blender = {"file": a.blend or "", "camera": a.cam or "", "start": a.start, "end": a.end}
    fields["blender"] = blender
    after = a.after if a.after is not None else None
    out(store.mutate(a.project, lambda d: store.insert_shot(d, after, fields))[1])


def cmd_set(a):
    def fn(d):
        item = store.find(d, a.collection, a.id)
        for pair in a.fields:
            key, _, raw = pair.partition("=")
            try:
                value = json.loads(raw)
            except ValueError:
                value = raw
            target = item
            *path, last = key.split(".")
            for p in path:
                target = target.setdefault(p, {})
            target[last] = value
        return item
    out(store.mutate(a.project, fn)[1])


def cmd_set_project(a):
    text = open(a.file).read() if a.file else a.value
    if text is None:
        sys.exit("error: give --file or --value")

    def fn(d):
        if a.field.startswith("style."):
            d.setdefault("style", {})[a.field[6:]] = text
        else:
            d[a.field] = text
    store.mutate(a.project, fn)
    print(f"set {a.field} ({len(text)} chars)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("projects").set_defaults(fn=cmd_projects)
    for name, fn in (("show", cmd_show), ("path", cmd_path)):
        p = sub.add_parser(name); p.add_argument("project"); p.set_defaults(fn=fn)
    p = sub.add_parser("notes"); p.add_argument("project"); p.add_argument("shot", nargs="?"); p.set_defaults(fn=cmd_notes)
    p = sub.add_parser("resolve"); p.add_argument("project"); p.add_argument("shot"); p.add_argument("note_id")
    p.add_argument("--reply", default=""); p.set_defaults(fn=cmd_resolve)
    p = sub.add_parser("next-path"); p.add_argument("project"); p.add_argument("shot")
    p.add_argument("--kind", default="previs"); p.add_argument("--ext", default="mp4"); p.set_defaults(fn=cmd_next_path)
    p = sub.add_parser("register"); p.add_argument("project"); p.add_argument("shot"); p.add_argument("file")
    p.add_argument("--kind", default="previs"); p.add_argument("--move", action="store_true"); p.set_defaults(fn=cmd_register)
    p = sub.add_parser("add-scene"); p.add_argument("project"); p.add_argument("--title", required=True)
    p.add_argument("--description"); p.set_defaults(fn=cmd_add_scene)
    p = sub.add_parser("add-shot"); p.add_argument("project"); p.add_argument("--scene", required=True)
    p.add_argument("--after"); p.add_argument("--id")
    for k in ("title", "description", "camera", "action", "blend", "cam"):
        p.add_argument(f"--{k}")
    p.add_argument("--duration", type=float); p.add_argument("--start", type=int, default=1)
    p.add_argument("--end", type=int, default=96); p.set_defaults(fn=cmd_add_shot)
    p = sub.add_parser("set"); p.add_argument("project"); p.add_argument("collection", choices=store.COLLECTIONS)
    p.add_argument("id"); p.add_argument("fields", nargs="+"); p.set_defaults(fn=cmd_set)
    p = sub.add_parser("set-project"); p.add_argument("project")
    p.add_argument("field", choices=("title", "outline", "script", "style.look", "style.consistency"))
    p.add_argument("--file"); p.add_argument("--value"); p.set_defaults(fn=cmd_set_project)
    a = ap.parse_args()
    try:
        a.fn(a)
    except (store.StoreError, StopIteration) as e:
        sys.exit(f"error: {e or 'not found'}")


if __name__ == "__main__":
    main()
