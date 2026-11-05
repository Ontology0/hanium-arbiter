# Culture-Fit product videos

The new product editions focus on the product, installation and the decision workflow. The earlier `culture-fit-demo-*` review videos remain preserved separately.

| Edition | Video | Voice | Captions |
|---|---|---|---|
| Korean | [culture-fit-product-ko-1080p.mp4](culture-fit-product-ko-1080p.mp4) | Harry Kim — Conversational, Korean; ElevenLabs Eleven v4, Generation 1 | [Korean SRT](culture-fit-product.ko.srt) |
| English | [culture-fit-product-en-1080p.mp4](culture-fit-product-en-1080p.mp4) | Daniel — Radio news host, English; ElevenLabs Eleven v4, Generation 1 | [English SRT](culture-fit-product.en.srt) |

Both editions are 180 seconds, 1920 × 1080, 30 fps, with 5,400 video frames. Both use the actual **English interface**. Conversation analysis supports **English and Korean**; there is no interface language selector. These editions have separate newly generated narration and captions in their respective languages.

The 143 seconds of UI footage were recorded with Chrome/Playwright from the public deployment and an isolated local first run. The other 37 seconds are original [Three.js product graphics](product-motion/README.md), with English labels shared by both editions. Pretendard captions use white text with selected cyan/yellow emphasis on a black canvas.

## What the footage shows

- Downloading the real source and OpenClaw Skill ZIPs; viewing the macOS and Windows setup instructions.
- An empty workspace from the downloaded source, actually started on macOS with `bash ./start-macos.sh`, port 8896 and a separate SQLite database inside the video work directory.
- A clearly separated transition to the public demo, in a fresh independent visitor context.
- A prepared English example: authority conflict → recorded analysis → original-message references → proposed priority → one-owner approval still unresolved → both-owner approval recorded → Review Agent as decision owner.
- Local MCP setup instructions, followed by an explanatory MCP/A2A/Skill connection diagram and the global MIT open-source Human-in-the-Loop (HITL) call to action.

The source ZIP shown on camera and the package used for first run have the same SHA-256: `58b0bf0c92cfe22870143898d5782f5940f36f5558a7d96e7b2b07723a0a181a` (390,899 bytes). This records the captured deployment, rather than guaranteeing future downloads remain byte-identical.

The Windows instructions are shown; a Windows machine was not used for this recording. The demo conversation is synthetic and reuses recorded analysis. Approval checkboxes are operator-entered records, not authenticated remote-owner actions. No new model analysis, external agent action or Slack delivery was triggered during capture. Source installation and configuration do not imply an external integration is already connected.

## Narration, captions and validation

The new scripts are [Korean](product-script-ko.txt) and [English](product-script-en.txt). The [storyboard](product-storyboard.json) maps the 22 cues to actual screen actions. ElevenLabs source MP3s and generation receipts are preserved under `work/elevenlabs/product-*`.

The Korean [caption overrides](product-caption-overrides-ko.json) use standard written names such as MCP, A2A, MIT, uv, OpenClaw and Human-in-the-Loop (HITL). Pronunciation spellings remain only in the speech script. The caption correction preserves the narration waveform, encoded audio and cue timing; the English edition remains unchanged.

Each source track is split only at measured pauses, at playback speed **1.0**, with silence added to scene slots. All 21 internal cuts are inside measured silence. The original final tail is preserved. Local Whisper transcription supports text/timing review; its recognition score is not a claim of speech quality or a human listening test. Three English caption boundaries move by 0.75, 0.40 and 0.35 seconds to accommodate natural speech without speeding it up.

- [Korean validation](product-validation-ko.json), [English validation](product-validation-en.json)
- [Korean audio provenance](product-narration-source-ko.json), [English audio provenance](product-narration-source-en.json)
- [Korean contact sheet](product-contact-sheet-ko.jpg), [English contact sheet](product-contact-sheet-en.jpg)
- [Actual capture receipt](work/product/capture-receipt.json), [downloaded-source first-run receipt](work/product/first-run-receipt.json)
- [Korean caption layout](product-caption-layout-ko.json), [English caption layout](product-caption-layout-en.json)

Validation checks full MP4 decoding, all stream durations, 5,400 frames, 1080p30, the last frame, subtitle bounds and the complete source audio. Burned captions are present. The optional internal subtitle track defaults to off to avoid duplicate automatic subtitles.

## Reproduction

The preserved raw recording, source audio, reviewed cut lists, fonts and motion clips are sufficient to render again without contacting ElevenLabs or calling a model:

```sh
uv run --with pillow python docs/video/render_product.py --language ko
uv run --with pillow python docs/video/render_product.py --language en
```

`record_product_ui.py` documents the real browser actions and blocks unexpected POSTs, including model calls. `prepare_product_local.py` downloads a source snapshot and launches a new isolated first-run workspace. It deliberately refuses to overwrite an existing first-run directory or use an occupied port. A new capture requires a separate preserved run directory and a currently checked deployment.

## Links and credits

- [Try Culture-Fit](https://culture-fit-demo-production.up.railway.app/)
- [How to use Culture-Fit](https://culture-fit-demo-production.up.railway.app/download)
- [MIT-licensed source](https://github.com/Ontology0/hanium-arbiter)
- [Detailed project and design sources](references.json)
- [Three.js product-motion sources and verification](product-motion/README.md)
- [Pretendard font provenance](fonts/sources.json)

Suggested titles include the required voice attribution:

`Culture-Fit | Open-source Human-in-the-Loop (HITL) | Korean | elevenlabs.io`

`Culture-Fit | Open-source Human-in-the-Loop (HITL) | English | elevenlabs.io`

The code's MIT license and the generated voice's terms are separate. These voices were generated through the user-authorized ElevenLabs web interface on the free account; the [official publishing guidance](https://elevenlabs.io/docs/help-center/legal/can-i-publish-the-content-i-generate-on-the-platform) requires attribution in the title for noncommercial sharing. The end card also gives a small ElevenLabs credit. No voice cloning was used.
