> ARCHIVO HISTÓRICO — conservado el 19 de octubre de 2026.
> No es un manual vigente ni acredita capacidades actuales.
> Consulta el [índice de documentación actual](../README.md).

> Mapa histórico, con cifras y observaciones no revalidadas. Consulta ../audit/2026-10-15.md.

# Kitok project guide

Short operational map for maintainers, users and coding assistants. The full
setup and command reference remains in [README.md](README.md).

## What Kitok is

Kitok is a local video production and publishing control plane. Python runs in
WSL, MoneyPrinterTurbo (MPT) runs separately on Windows, and both communicate
over HTTP.

```text
content/config -> Kitok -> MPT and/or local Fish + Pexels + FFmpeg
               -> validation -> outputs/ready
               -> optional Cloudinary -> optional Buffer
```

Generation and publishing are separate. Producing a READY video never publishes
it automatically.

## What it can do

- Manage a validated content queue, editorial states and local schedules.
- Generate short Pexels explainers through MPT.
- Generate Fish Audio dialogue videos with local backgrounds, character poses
  and locally timed subtitles.
- Generate the supported local single-speaker format (`rick_es` + `random`).
- Generate 16:9 Loose Thread long-form videos from a dedicated JSON and text
  script through `longform.py`. MPT remains the default; Native is an explicit
  experimental renderer.
- Validate and normalize MP4 output before marking it READY.
- Preview, schedule and reconcile posts through Buffer, with Cloudinary hosting.
- Operate through CLI, Streamlit, or the React/FastAPI studio.
- Run smoke tests and compare arbitrary Fish `reference_id` values without
  generating a video.

## What it does not do

- It is not a public or multi-user web service; its web servers bind locally.
- It does not publish unless publishing is enabled and explicitly confirmed.
- It does not generate queue scripts or editorial content automatically.
- It does not run video jobs in parallel.
- It does not accept arbitrary dialogue speakers, voices or character layouts;
  they must exist in `presets/generation_profiles.json`.
- Long-form does not support `visual_sections`. Stock keywords are global and
  consumed in narrative order, but they are not tied reliably to TTS timestamps.
- Long-form does not perform per-sentence semantic stock selection, automatic
  zoom/pan, Ken Burns effects or transitions between stock clips.

## Generation paths

| Path | Input | Audio | Visual/render |
| --- | --- | --- | --- |
| Short Pexels explainer | `content_queue.json` | MPT voice | MPT stock + render |
| Local explainer | `content_queue.json` | Fish | Local background + Kitok FFmpeg |
| Dialogue | `content_queue.json` | One Fish call per turn | MPT Pexels or local background, then Kitok FFmpeg |
| Long-form (default) | Dedicated JSON + `.txt` | Fish through MPT | MPT 16:9 render, then Kitok FFmpeg post-process |
| Long-form Native (experimental) | Same JSON + `.txt` | Kitok Fish, one coherent call | Kitok Pexels timeline + chunked FFmpeg/NVENC |

The long-form post-process adds loudness normalization, optional music, a visual
fade-in and a held-frame fade to black. It deliberately leaves narration volume
untouched at the ending.

## Sources of truth

- `content_queue.json`: active short-form content definitions.
- `state/state.json`: attempts, task IDs, output paths and publishing state.
- `presets/mpt_default.json`: normal MPT generation defaults.
- `presets/generation_profiles.json`: voices, visual profiles and characters.
- `.env`: Kitok endpoints, credentials and runtime settings; never commit it.
- MPT `config.toml`: MPT-side Fish model and credentials; never commit or expose it.
- `content/longform/<n>/*.json`: long-form definitions.
- `content/longform/<n>/*.txt`: narration scripts.

Long-form `script_file` paths are resolved from the repository root, not relative
to the JSON file. A new long-form submission is rejected if the narration does
not end in `.`, `!`, `?`, `"`, `'`, `]` or `)`.

## Main entry points

```bash
# Validate local queue/configuration
python main.py --dry-run

# Generate all eligible queue items, or one item
python main.py
python main.py --id CONTENT_ID

# Inspect state and MPT connectivity
python main.py --status
python main.py --check-mpt

# Streamlit control panel
python main.py --dashboard

# FastAPI backend for the React studio
python -m kitok.api

# React development server (separate terminal)
cd frontend
npm run dev

# Long-form
python longform.py content/longform/1/example.json

# Explicit experimental Native path; MPT remains the default and fallback
python longform.py content/longform/1/example.json --renderer native

# Add cache/selection/scale decisions and safely quoted FFmpeg commands
python longform.py content/longform/1/example.json --renderer native --verbose

# Isolated Native smoke (writes only below outputs/smoke)
python scripts/native_longform_smoke.py --start-over

# Compare NVENC presets on the exact same completed smoke input/audio
python scripts/benchmark_nvenc.py outputs/smoke/native_longform_smoke_001.mp4

# Fish voice comparison; --voice may be repeated
python scripts/test_fish_voices.py
python scripts/test_fish_voices.py --voice "my_voice=REFERENCE_ID"

# Tests
pytest -q
```

Use `--publish-dry-run` before any confirmed publishing command. The detailed
queue, scheduling, regeneration and Buffer commands are documented in README.

## External dependency

The default long-form V1.1 behavior still depends on the patched
MoneyPrinterTurbo Portable installation. MPT must be restarted after changing
its Python code or `config.toml`. Native is opt-in and uses `FISH_API_KEY` plus
`PEXELS_API_KEY` from Kitok's `.env`; it never reads MPT `config.toml`. The
active Fish synthesis model is `s2.1-pro-free`; a Fish `reference_id` selects a
voice independently of that synthesis model. The Loose Thread default speed is
`0.98`; an explicit legacy JSON value such as `0.95` remains authoritative.

Avoid submitting a second long-form task when a marker already exists in
`outputs/longform/tasks/`. Resume the saved task or explicitly start over.

## Current performance profile

The clearest bottlenecks, before doing a formal benchmark, are:

1. **Final FFmpeg composition for local short videos.** It scales and encodes
   `1080x1920` at 30 fps with `libx264`, preset `medium`, while applying character
   overlays and subtitles. Recent logs show roughly 45-60 seconds here after the
   Fish calls have finished.
2. **Sequential Fish dialogue calls.** Every turn is synthesized and measured
   before the next one starts. A typical seven-turn item spends roughly 15-25
   seconds waiting for Fish.
3. **Serial queue processing.** `Pipeline.process()` completes one whole item
   before starting the next, so network waits and CPU rendering do not overlap.
4. **Long-form double encoding.** MPT first renders the documentary; Kitok then
   performs another complete `libx264 medium` pass for fades, normalization and
   music. On an 8-14 minute video this second pass can be substantial.
5. **Stock search/download inside MPT.** This is likely relevant to long-form,
   but Kitok currently lacks enough stage timing from MPT to rank it accurately.

Copying finished 25-37 MB shorts into the ready folders takes only around one or
two seconds in recent runs and is not the main bottleneck.

Before optimizing, record stage timings for one short and one long-form render.
The least invasive experiment is comparing FFmpeg `medium` with `fast` or
`veryfast`; removing the long-form second encode would save more time but requires
a more invasive MPT integration. Parallel generation is unlikely to help while
CPU encoding is saturated.

## Repository notes

The implementation is mostly well separated under `src/kitok`, with focused
tests under `tests`. The root is less tidy: pilots, backups and import JSON files
sit beside production entry points. Do not move them blindly because some are
working data. A future cleanup can place examples under `examples/`, old notes
under `docs/archive/`, and remove generated `*.egg-info` metadata from version
control after checking that nothing depends on it.

When changing behavior, preserve existing queue/state files, avoid automatic
retries of submission POSTs, and test the affected generation path rather than
assuming all formats use the same pipeline.

## Native long-form migration boundary

Renderer selection is explicit: omitted or `--renderer mpt` preserves the old
path; `--renderer native` selects the experimental path. Native has no access to
queue/state/publishing code, never creates an MPT task, refuses to replace an
existing output without `--start-over`, and writes through an atomic temporary
file. A Native failure therefore leaves existing output and MPT recovery
history untouched; fallback is a deliberate rerun with `--renderer mpt`, never
an automatic second submission.

Native owns these reusable modules:

- `kitok.providers.pexels`: search, normalized metadata and atomic downloads.
- `kitok.stock`: provider-neutral assets, search/asset caches and 16:9/9:16
  selection. Exact 1080 output is preferred to 4K; 720p is a fallback.
- `kitok.longform.timeline`: deterministic 5.5-8.5 second hard-cut slots whose
  final boundary is the measured narration duration. `VisualSection` already
  represents future section/keywords/audio-start/audio-end data without
  pretending that alignment exists today.
- `kitok.media`: ffprobe validation and FFmpeg command/render infrastructure.
- `kitok.rendering`: the MPT adapter and isolated Native renderer.

The video renderer limits each FFmpeg graph to 12 source decoders. It encodes
compatible H.264 chunks, concatenates them by stream copy, then mixes and
two-pass-normalizes the final audio master while copying video. Every video frame is therefore encoded
once, with no full-video re-encode after concat. This is intentionally safer
than opening roughly 100 inputs in one graph on a 4 GB GPU. Native runtime-probes
NVENC and falls back to `libx264 medium CRF 18` only in `auto` mode. Its
quality-first NVENC settings are VBR HQ, CQ 18, 20 Mbps maxrate, 40 Mbps buffer,
full-resolution multipass, spatial/temporal AQ and lookahead 32. Preset `p5` is
the current default based on the benchmark below.

The final aligned 30-second 1080p benchmark used one identical high-motion AV1
input segment and identical audio/settings for all presets. Both encoding and
the metric reference use the same explicit 30 fps cadence. GPU utilization was
low (roughly 5.5-6.1% average, 7-9% peak) because software AV1 decode was the
limiting stage in this particular benchmark.

| Preset | Elapsed | Speed | Size | Avg bitrate | SSIM | PSNR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| p4 | 8.17 s | 3.67x | 73.98 MB | 19.73 Mbps | 0.993651 | 48.2287 |
| p5 | 8.81 s | 3.41x | 73.95 MB | 19.72 Mbps | 0.993756 | 48.2505 |
| p6 | 8.65 s | 3.47x | 73.97 MB | 19.73 Mbps | 0.993778 | 48.2706 |
| p7 | 8.59 s | 3.49x | 73.97 MB | 19.73 Mbps | 0.993778 | 48.2706 |

P6 and P7 were byte-identical. Representative side-by-side frames showed no
useful P5/P6 improvement, and their 0.000022 SSIM / 0.020 dB PSNR delta is not a
meaningful visual gain. P5 is therefore the quality-first recommendation until
the isolated casino/low-light smoke can be inspected. P4 remains an explicit
faster option, not the default.

Pexels caches are independent from production state:

```text
cache/pexels/searches/   query/orientation/page -> normalized candidate metadata
cache/pexels/videos/     asset ID -> validated MP4 plus metadata sidecar
```

`.part` files are never cache hits. Both cache classes expose an explicit
`clear()` method; do not clear them as a side effect of rendering.

### MPT functionality audit

Legend: A = necessary product behavior, B = already native in Kitok, C = small
clean reimplementation, D = unnecessary for Native Loose Thread V1.

| Capability | Class | Migration decision |
| --- | --- | --- |
| Fish synthesis | A+B | Reuse `FishVoiceClient`; one request, literal `[]` tags, speed 0.98, temperature 0.8, top-p 0.7. |
| Pexels search/download | A+C | Kitok provider with separate search and asset caches; no MPT code copied. |
| Material selection/resolution | A+C | Native scoring prefers 1920x1080, then nearest adequate source, then lower-resolution fallback; supports 1080x1920 target later. |
| Trim and source offsets | A+C | Timeline-authoritative FFmpeg trims; no per-stock temporary transcode. |
| Scale/crop/cover | A+B | Shared FFmpeg filters; only performed during the clip's single encode. |
| Timeline/hard concat | A+C | Measured narration is authoritative; deterministic keyword order and non-repetition where alternatives exist. |
| Subtitles | D (long-form) | Loose Thread currently disables them. Existing short subtitle behavior remains untouched. |
| Background music/audio mix | A+B | Music remains 0.05 and `amix normalize=0`; narration has no fade-out. Two-pass loudnorm runs after the mix, with 0.3 dB AAC headroom so the decoded master respects the requested true-peak ceiling. |
| Encoding | A+B | Shared FFmpeg with NVENC runtime probe and x264 fallback. |
| MPT task API/polling/artifact transfer | D (Native) | Preserved only for the MPT renderer/fallback. |
| Output validation | A+B | Native validates geometry, fps, codecs, duration and exposes probe/loudness data for smoke reports. |

This is a clean Kitok implementation based on required behavior and public API
shapes. No MPT source code was copied, so no MPT license notice was imported.
If substantial MPT code is ever considered later, inspect its exact version's
license first and retain every required notice.

### Shorts still on MPT

Pexels explainers still depend on MPT for voice synthesis, Pexels acquisition,
stock timeline, subtitles and final render. Dialogue with `visual_profile=pexels`
still uses MPT for its silent Pexels visual before Kitok adds measured Fish audio,
characters/subtitles; local gameplay/random paths do not need MPT for visuals.

Shorts can directly reuse the new Pexels provider/caches, stock selector with a
1080x1920 target, ffprobe/FFmpeg/NVENC layer and renderer result/timing model.
Removing MPT from shorts still requires a vertical timeline policy, integration
of the existing local subtitle timing/style, explainer voice parity, dialogue
visual-duration handling, vertical smoke comparisons, and an opt-in selector in
the queue pipeline. That selector must be introduced without changing current
state transitions or READY semantics. The main risks are subtitle parity,
vertical crop quality, recovery/idempotency across queued jobs, and accidentally
changing production defaults; none of those integrations are attempted here.
