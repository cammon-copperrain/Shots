---
description: Apply pending shot notes in Blender, re-render previs, and mark notes done
argument-hint: <project> [shot]
---

Project and optional shot: $ARGUMENTS

1. `python3 shots_cli.py notes <project> [shot]` lists the pending notes with each shot's
   Blender file, camera and frame range.
2. For each shot, make the changes the notes ask for in its .blend: camera position/lens/move
   for framing, character/object animation for blocking, keyframe timing and frame range for
   timing. If a note is ambiguous, ask me instead of guessing. If the shot has no .blend yet,
   build a simple blocking scene (proxy characters, set dressing from the environment
   sheet description, camera `CAM_<shot_id>`) and set the shot's `blender` field.
3. Save the .blend, render previs to the path from `next-path`, and `register` it
   (see CLAUDE.md, "Previs render").
4. If the frame range changed, update `blender.start`/`blender.end` and `duration` (seconds at
   the scene's fps) with `shots_cli.py set`.
5. `shots_cli.py resolve <project> <shot> <note_id> --reply "<what you changed>"` for each note.
   Leave a note pending if you couldn't do it, and tell me why.

The app picks up new versions and resolved notes on its own within a few seconds.
