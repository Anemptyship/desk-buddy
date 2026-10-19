# Demo film pipeline

Produces `DeskBuddy_Demo.mp4` (1920×1080, 30 fps, English only) from the recorded desk take,
the real player code, and synthesized sound. Nothing is hand-animated: every Bricki frame comes
from the same brain, place graph and renderer the live player uses, stepped at an exact 30 fps.

```sh
# 1. build and serve the player (offline.html is the frame-exact render page)
cd player && pnpm install && pnpm build && pnpm preview --port 4173 &

# 2. 60 fps motion-interpolated plate (smooth slow motion)
mkdir -p /tmp/work/plate60
ffmpeg -i player/public/scene/desk.mp4 \
  -vf "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" \
  -start_number 0 /tmp/work/plate60/%05d.png

# 3. render Bricki per shot, then composite + mix + encode
cd video && npm install
python3 film.py render
python3 film.py compose DeskBuddy_Demo.mp4
```

`WORK` and `PLATE60` override the scratch folders. `CHROME_PATH` points at a local Chrome;
otherwise the bundled `@sparticuz/chromium` is used (software WebGL, ~0.5 s/frame).

## With Gemini 4 Argon

```sh
GEMINI_API_KEY=... uv run desk-buddy perceive   # rewrites player/public/scene/objects.json
```

When `objects.json` carries `"source": "gemini-4-argon"`, the film's desk-map and how-it-works
shots credit Argon automatically. Without it, the film never claims Argon produced the map:
the current map is hand-placed from raycast frame points.

## Files

| File | Role |
| --- | --- |
| `film.py` | Shot list, plate time-remapping, follow camera, compositing, encode |
| `graphics.py` | Cards (tethered pill → full card), chips, titles, key press, desk-map drawing |
| `audio.py` | Synthesized music bed, foley (steps, landings, grabs), Bricki chirps, UI sounds |
| `scene.py` | Python mirror of the camera track and desk geometry for overlays |
| `render.mjs` | Drives `offline.html` in headless Chrome: simulate a shot, render RGBA frames |
