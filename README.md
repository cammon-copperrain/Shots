# Shots

A local app for making AI films shot by shot: outline → script → scenes → shot list → Blender
previs → notes → Seedance generation on fal.ai, with every result landing back on the board in
place of its previs.

- **The app** (this repo) runs on your Mac and opens in the browser. It has no AI inside and
  needs no Claude API key.
- **Claude Code** is the AI: it writes, breaks down the script, and drives Blender
  (slash commands in `.claude/commands/`, rules in `CLAUDE.md`).
- **fal.ai** generates the video. It's paid per generation with your fal key.
- **Projects** are folders in Dropbox. One app, as many projects as you want; switch any time.

## First-time setup on the Mac Studio

1. Get the code:
   ```
   cd ~/Developer        # or wherever you keep code
   git clone https://github.com/cammon-copperrain/Shots.git
   cd Shots
   ```
2. Make sure `python3` works in Terminal. If macOS offers to install developer tools, accept.
   For animatic export also run `brew install ffmpeg`.
3. Double-click **`Shots.command`** (first time: right-click → Open, because macOS blocks
   downloaded scripts). It sets itself up, creates `config.json`, and opens the app.
4. Edit `config.json`:
   - `fal_key`: your fal API key
   - `projects_dir`: where projects live (default `~/Library/CloudStorage/Dropbox/Shots Projects`;
     set that Dropbox folder to *Available offline* so Blender can open files)
   - `blender_path`: default `/Applications/Blender.app/Contents/MacOS/Blender`
   - `fal_endpoint` / `fal_defaults`: the Seedance model and default fields
5. Close the Terminal window and double-click `Shots.command` again.

Drag `Shots.command` to the Dock to start it in one click from then on.

## Daily use

1. **Start:** double-click `Shots.command` → pick or create a project.
2. **Write:** *Script & Scenes* tab holds the outline, script, the look/style, and
   "keep consistent" notes. In Claude Code (opened in this folder) run `/breakdown <project>` to
   turn the script into scenes and shots, or add them by hand.
3. **Assets:** *Characters & Sets* tab holds character sheets and environment/set references:
   images plus a description. Tick them on scenes or shots.
4. **Previs:** Claude Code builds blocking in Blender and renders each shot
   (`/apply-notes`, or ask it directly). You can also tweak a .blend by hand and click
   **Render previs** on the shot, or upload a clip under *Versions*.
5. **Notes:** add framing/blocking/timing/camera/acting notes on a shot, then click
   **Copy /apply-notes** and paste into Claude Code. It changes Blender, re-renders, and marks
   the notes done; the board updates on its own.
6. **Coverage:** the **+** between cards inserts a shot (sh010 → sh015 → sh020).
7. **Generate:** open **Seedance prompt** on one shot, or tick several shots and click
   **Build Seedance prompt**. The prompt is assembled from the look, consistency notes, scene and
   shot descriptions, notes marked *in prompt*, and the character/set sheets (@Image refs).
   Choose each previs as its own @Video, one combined animatic, or no video. Edit the text, then
   **Send to fal.ai**.
8. **Result:** when the job finishes, the clip becomes the shot's current version (a
   multi-shot clip is shared across those shots, each playing its planned segment). Every
   version is kept, so you can go back to previs, change it, and regenerate.

## Project folder

```
<projects_dir>/<Project>/
  project.json         outline, script, scenes, shots, notes, assets, jobs
  blender/sc010.blend  one per scene, camera per shot named CAM_sh010
  shots/sh010/v001_previs.mp4, v002_seedance.mp4 …
  assets/characters/…, assets/environments/…
  animatics/
```

## Seedance on fal: check before relying on it

From fal's docs (not verified against the live API from here):
reference-to-video takes up to 30 images, 10 videos and 10 audio clips, referenced as
`@Image1`, `@Video1`…; each video reference must be 1.8–30.2 s. A `draft` flag (480p preview,
completable to 1080p within 7 days) is documented on the **image-to-video** endpoint; it isn't
confirmed for reference-to-video. The request is fully editable in the dialog. Set
`fal_defaults` in `config.json` once you've confirmed the field names on the model's API page.

## Optional: use it away from the studio

The app only listens on the Mac itself. To reach it from a laptop or phone, install
[Tailscale](https://tailscale.com) on both, change `--host 127.0.0.1` to `--host 0.0.0.0` in
`Shots.command`, and open `http://<mac-studio-tailscale-name>:8765`. The app has no login, so
only do this on a private network like Tailscale.
