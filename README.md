# Desk Buddy

A tiny interactive companion on your actual desk. Built by **pico banana — Hanbin Bae (@anemptyship)** for the Google DeepMind AI Hackathon.

Meet Bricki: an original 4 cm block-toy character rendered live in Three.js over synchronized footage of a real desk. It walks, rests on a laptop, climbs a coffee cup, and jumps over to deliver messages and permission requests.

## Run the playable demo

```sh
cd player
pnpm install
pnpm dev
```

Open the local Vite URL in Chrome. Click Start, then use the buttons or keyboard:

| Key | Action |
| --- | --- |
| 1 | Walk on the desk |
| 2 | Sit on the laptop |
| 3 | Climb the cup and sit on its rim |
| 4 | Deliver a message |
| 5 | Ask for permission |
| 6 | Urgent notification |
| Enter / Backspace | Allow / Later |
| - / + | 2.5 cm / 4 cm character |
| G / F1 | Surface debug / implementation information |

Guided demo runs the real application transitions. Record live demo captures 68 seconds of the actual composite canvas with audio and exports WebM. Convert for YouTube with:

```sh
ffmpeg -i DeskBuddy_Live_Demo.webm -vf fps=30 -c:v libx264 -crf 19 -pix_fmt yuv420p -c:a aac -movflags +faststart DeskBuddy_Live_Demo.mp4
```

The player uses cached assets and needs no API key. Production build: `pnpm build`.

## How it works

Python prepares tone-mapped, rectified real footage and camera samples synchronized to video timestamps. A measured 14-inch MacBook Pro anchors approximate metric scale. Three.js renders a procedural jointed character, surface shadows, and invisible depth-writing laptop/cup proxies. Notifications and permission choices drive actual application state.

Nano Banana created the original character design reference. Omni concept clips were explored separately; they are **not** used as the playable avatar or in the live demo recording. Runtime voices are cached macOS system speech. Animation is procedural code.

## Prototype limitations

The background is prerecorded, not a live headset camera. Object geometry and contact/shadow matching are approximate. Notification and permission events are local demo events; the permission card does not request actual camera access. This prototype does not claim drift-free reconstruction or production AR tracking. The initial laptop calibration measured about 0.47 px reprojection RMS; this does not measure whole-scene accuracy.

## Offline pipeline

```sh
uv sync
uv run desk-buddy --help
uv run pytest
```

See [pipeline notes](docs/PIPELINE.ko.md). Keep API credentials in an ignored `.env`; never commit credentials. The public player includes only the rectified desk clip and cached runtime assets, without the original MOV metadata.

Original code is MIT licensed. Third-party libraries and media retain their respective rights.
