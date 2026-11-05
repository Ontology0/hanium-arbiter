# Culture-Fit product motion

Product-only English diagrams shared by the Korean-voice and English-voice videos. These explanatory diagrams complement actual installation and dashboard recordings; they do not depict a live agent call or a completed external action.

| Clip | Duration | Product-video position | Content |
|---|---:|---|---|
| `problem.mp4` | 16 s | 00:00–00:16 | Shared information and delegated authority; two owners and two agents; who can decide? |
| `connections.mp4` | 8 s | 02:39–02:47 | Agent clients → MCP / A2A / Skill → Culture-Fit |
| `cta.mp4` | 13 s | 02:47–03:00 | Human-in-the-Loop (HITL), MIT open source, global developer audience, source and installation links |

Each file is silent H.264, 1920×1080, 30 fps. The lower 180 pixels are reserved for the final narration captions. Black background, white Pretendard, cyan/yellow emphasis and 24 px gray diagram credits follow the requested style. No history of the team appears.

`product-motion.js` constructs actual Three.js scenes, meshes, line geometry and text textures. `render.py` renders deterministic WebGL frames in headless Chrome and pipes them into ffmpeg. Existing local Three.js 0.180.0 and Pretendard 1.3.9 assets in `../motion/work/` are reused; no remote asset fetch is needed while rendering. Font provenance and license are in `../fonts/sources.json` and `../fonts/LICENSE`.

```sh
uv run --with playwright python docs/video/product-motion/render.py
```

Options: `--previews-only`, `--scene problem`, `--scene connections`, `--scene cta`. The HTTP preview server chooses an unused loopback port by default; `--port` can select a port explicitly. It closes at the end of rendering. Existing `docs/video/motion/` files are unchanged.

`check_spacing.py` checks each encoded frame's visible text bounds, including neon padding, against labels, rings and connectors. Explicit text inside protocol/product/question nodes is intentional. Icon-internal strokes are decorative; no label is superimposed on them. `spacing-validation.json` records zero label overlaps and the measured clearances. `render-validation.json` records JavaScript/request failures, codec metadata, frame counts and SHA-256 hashes. Preview PNGs show the completed layouts.

Product links on the final card:

- Source: https://github.com/Ontology0/hanium-arbiter
- Installation and demo: https://culture-fit-demo-production.up.railway.app/download

The source code is MIT-licensed. This code-license label does not assign a license to the independently generated narration. Narration provenance and required ElevenLabs attribution belong in the final video description and upload metadata.
