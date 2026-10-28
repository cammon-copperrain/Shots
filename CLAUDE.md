# Shots — instructions for Claude Code

Shots is a local app for AI-film previs → Seedance generation. **You (Claude Code) are the
AI for this app**: writing, breakdown, and Blender work happen in this session. The app itself
has no AI; it shows the board, collects notes, builds Seedance prompts, and sends jobs to fal.ai.
Do not add Claude API calls to the app.

## Where things live

- Projects: one folder per project under `projects_dir` from `config.json`
  (default `~/Library/CloudStorage/Dropbox/Shots Projects`). Find a project with
  `python3 shots_cli.py path <project>`.
- `project.json` in that folder is the single source of truth: outline, script, style,
  scenes, shots (in board order), characters, environments, jobs.
- Media is referenced by project-relative paths:
  - `blender/<scene_id>.blend`: one .blend per scene, one camera per shot named `CAM_<shot_id>`
  - `shots/<shot_id>/vNNN_<kind>.mp4`: versions (`previs`, `still`, `seedance`)
  - `assets/characters/<id>/…`, `assets/environments/<id>/…`: reference sheets
  - `animatics/`: exported animatics

## Rules

- **Never hand-edit `project.json` while the app may be open.** Use `shots_cli.py`, which writes
  atomically: `show`, `notes`, `resolve`, `next-path`, `register`, `add-scene`, `add-shot`, `set`.
  Run `python3 shots_cli.py -h` for the full list.
- Never overwrite an existing version file. Render to the path `next-path` prints, then `register` it.
- Shot ids are `sh010`, `sh020`… Inserted shots fall between (`sh015`) or take a letter (`sh010A`).
  Keep them stable: notes, versions and folders hang off them.
- Each shot's `blender` field (`file`, `camera`, `start`, `end`) is how the app re-renders it.
  Keep it accurate whenever you build or change a shot in Blender.

## Previs render

Headless Workbench render (looks like a viewport playblast):

```
OUT=$(python3 shots_cli.py next-path <project> <shot>)
"$BLENDER" -b "<project dir>/blender/sc010.blend" -P tools/blender_render_shot.py -- \
  --camera CAM_sh010 --start 1 --end 96 --out "$OUT"
python3 shots_cli.py register <project> <shot> "$OUT"
```

`$BLENDER` is `blender_path` from `config.json`. If you're driving a live Blender session
(e.g. via a Blender MCP), save the .blend first, then render the same way, or render from the
live session to the `next-path` output and `register` it.

## Notes

Notes on a shot have `type` (framing, blocking, timing, camera, acting, general), `status`
(`pending`/`done`) and `to_prompt` (whether the note is carried into the Seedance prompt).
Framing/blocking/timing notes are usually Blender work; camera/acting notes usually need to
stay consistent in generation too. When you apply a note, resolve it with a one-line `--reply`
saying what changed.
