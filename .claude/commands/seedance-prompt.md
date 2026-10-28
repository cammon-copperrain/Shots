---
description: Tighten the Seedance prompt text for one or more shots
argument-hint: <project> <shot> [shot ...]
---

Project and shots: $ARGUMENTS

1. Build the app's assembled prompt to start from:
   `.venv/bin/python -c "from app import store, prompt; import json,sys; print(json.dumps(prompt.build_request(store.load(sys.argv[1]), sys.argv[2:])['payload'], indent=2))" <project> <shots...>`
2. Rewrite each shot's section so it's specific and filmable: subject, action, camera move,
   lens/framing, light. Keep @Image/@Video references and their numbering exactly as assembled.
   Keep every consistency note. Don't invent story beats.
3. Show me the rewrite. On OK, save each shot's version into its `prompt_override` with
   `shots_cli.py set <project> shots <id> prompt_override="..."`, so the app uses it.
