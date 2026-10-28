---
description: Break a project's script into scenes and a shot list (writes into the Shots project)
argument-hint: <project> [extra direction]
---

Project and direction: $ARGUMENTS

1. Run `python3 shots_cli.py show <project>` and read `project.json` (outline, script, style,
   existing scenes/shots, characters, environments) at `python3 shots_cli.py path <project>`.
2. If there's an outline but no script, draft the script first (screenplay format), show it to me,
   and on OK save it with `python3 shots_cli.py set-project <project> script --file <draft.md>`.
3. Propose the scene list and shot list as a table: id, scene, duration, description,
   camera (lens/framing/move), action, characters, environments. Aim for shots of 2–8 s.
   Wait for my OK before writing anything.
4. On OK, create scenes with `add-scene` and shots with `add-shot` (in order, with
   `--blend blender/<scene_id>.blend`; the camera name defaults to `CAM_<shot_id>`). Don't touch scenes/shots that already
   exist unless I said to. Link characters/environments with
   `shots_cli.py set <project> shots <id> 'character_ids=["ch_…"]'`; create missing ones by
   asking me first.
5. Finish with `shots_cli.py show <project>`.
