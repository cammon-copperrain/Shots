"""Headless previs render of one shot, Workbench engine (looks like a viewport playblast).

    Blender -b scene.blend -P tools/blender_render_shot.py -- \
        --out /path/v003_previs.mp4 --start 1 --end 96 [--camera CAM_sh010] [--res 1280x720]

Viewport (OpenGL) render needs a window, so it doesn't work in -b mode; Workbench does.
"""

import argparse
import sys

import bpy


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=96)
    ap.add_argument("--camera", default="")
    ap.add_argument("--res", default="1280x720")
    return ap.parse_args(argv)


def main():
    args = parse()
    scene = bpy.context.scene
    if args.camera:
        cam = bpy.data.objects.get(args.camera)
        if cam is None or cam.type != "CAMERA":
            raise SystemExit(f"camera {args.camera!r} not found in {bpy.data.filepath}")
        scene.camera = cam
    scene.frame_start, scene.frame_end = args.start, args.end

    r = scene.render
    r.engine = "BLENDER_WORKBENCH"
    w, h = (int(x) for x in args.res.lower().split("x"))
    r.resolution_x, r.resolution_y, r.resolution_percentage = w, h, 100
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "MATERIAL"

    img = r.image_settings
    if hasattr(img, "media_type"):  # Blender 5.x splits image vs video output
        img.media_type = "VIDEO"
    img.file_format = "FFMPEG"
    r.ffmpeg.format = "MPEG4"
    r.ffmpeg.codec = "H264"
    r.ffmpeg.constant_rate_factor = "MEDIUM"
    r.ffmpeg.audio_codec = "NONE"
    r.use_file_extension = False
    r.filepath = args.out

    bpy.ops.render.render(animation=True)


main()
