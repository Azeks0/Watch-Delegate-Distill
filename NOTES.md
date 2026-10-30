# Watch, Delegate, Distill — SAM 3.1 pipeline notes

State as of 2026-10-30. Budget spent across all work so far: **6.1 of 60 minutes**.

---

## 1. What changed

### Structure

`sam_ego4d.py` was a single 924-line script. It is now a thin entry point over a
`sam_pipeline/` package. The CLI is byte-for-byte identical — `--help`, `ego4d --help` and
`episode --help` all produce exactly the output they did before.

| module | holds |
|---|---|
| `config.py` | constants, clip-selection vocabulary, hold/pass thresholds, prompt fallbacks |
| `budget.py` | the shared request ledger |
| `clips.py` | narration parsing, `select_clips` |
| `clip_index.py` | which window of which parent video each `<clip_uid>.mp4` covers |
| `sources.py` | `VideoLibrary` — resolves `(video_uid, start, end)` to a file + offset |
| `video.py` | ffmpeg / ffprobe |
| `sam_client.py` | Meta Model API transport |
| `masks.py` | COCO RLE codec + decode cache |
| `detections.py` | `parse_sam`, `Det`, `dump_masks` |
| `analysis.py` | holders, object track, events, steps |
| `pipeline.py` | `segment_video` — one video through SAM |
| `preview.py` | the annotated `preview.mp4` |
| `ego4d.py` / `episode.py` | the two modes |
| `credentials.py` / `cli.py` | key, argument parsing, entry point |

### Four bugs found and fixed

**1. Resolution was silently destroying the tool.** This was the big one. At the old
`--width 640` default, `paintbrush`, `paint brush` and `brush` all returned *empty streams*
on a clip where the brush is plainly visible. The same clip at 1280px returned 27 KB of
detections at confidence 0.91. A held brush at 640px is a few dozen pixels.

SAM is billed `max(frames, 50) / fps` — **there is no resolution term, so resolution is
free**. Default is now `--width 1280`. This alone took tool detection from 0/1 to 20/21.

**2. Empty responses poisoned the cache permanently.** `segment_video` treated any existing
`sam_<role>.txt` as a cache hit. A 0-byte "SAM found nothing" response was therefore reused
forever, free, on every subsequent run — so a retry could never happen and the failure
looked reproducible. Now a zero-length file is never a cache hit, and a response is only
written if it parsed to actual detections. Concepts that returned nothing are recorded in
`sam_<role>_empty.json` so you don't re-pay for them; `--retry-empty` overrides.

**3. No fallback when a concept doesn't fire.** Narration vocabulary and SAM's concept
vocabulary disagree. `object_fallbacks()` gives each tool an ordered chain
(`paintbrush → paint brush → brush → brush held in hand → tool held in hand → object held in hand`).
`--object-attempts N` (default 3) bounds the spend. In the 21-clip run the chain rescued 2
clips. The winning concept is recorded in `score.json` under `quality.object_prompt`.

**4. Clip files were unaddressable.** `ego4d` mode cut from `full_scale` videos at absolute
video timestamps, but everything downloaded is `clips/` — named by `clip_uid`, covering one
window of a parent video. `clip_index.py` + `sources.py` resolve this, and `cut_clip` is now
called with `src.local(c.start)`. `score.json` records `source.file` and
`source.file_offset_s`. New flag `--clip-annotations DIR`, defaulting to the folder
`--narrations` lives in, so no extra arguments are needed.

### Hold/pass detection retuned

Tuned offline against the cached SAM output of all 21 clips — no API cost — scoring against
the narration's own giver/taker.

| parameter | was | now | why |
|---|---|---|---|
| `HOLD_OVERLAP` | 0.15 | **0.10** | a hand grips a brush near its end, so only a sliver of the tool's box sits inside the hand's |
| `HOLD_BOX_PAD` | 0.1 | **0.30** | egocentric foreshortening |
| `PASS_MAX_UNHELD_FRAMES` | 0 (no gap allowed) | **25** (0.83s) | mid-handover the tool is occluded by both hands |

The old rule demanded `A alone → both → B alone` with no gap, so a real pass where the tool
vanishes for a few frames was emitted as `release` + `drop` + `grasp`. A `drop` is no longer
emitted for an unheld stretch that is part of a detected handover.

**Result: 5/21 passes → 12/21.** Narration agreement 4 → 11.

---

## 2. What to use from the videos

**12 usable passes across 7 clip files.** All live in `Downloads\v2\clips\`. The offset is
where the 6-second window starts inside that file.

| clip file | offset (s) | tool | direction | tool visible | SAM concept |
|---|---|---|---|---|---|
| `4a2af66c-cf0f-42b8-a0ca-ba182f7fc9a3` | 241.72 | pen | right→left | **1.00** | `pen` |
| `0e9362ba-1c57-4a6b-ae08-46cdb8e33752` | 128.38 | paintbrush | right→left | **0.99** | `paintbrush` |
| `ccf8a14a-e815-4a2d-8ddc-8863b4e158a6` | 18.51 | paintbrush | right→left | **0.92** | `paintbrush` |
| `ccf8a14a-e815-4a2d-8ddc-8863b4e158a6` | 275.67 | paintbrush | right→left | **0.87** | `paintbrush` |
| `a81b005c-38a2-4913-afe3-55026607a124` | 230.74 | paintbrush | right→left | 0.82 | `paintbrush` |
| `4713085d-6f54-42f6-a4a7-1e0cdf438df8` | 118.71 | paintbrush | left→right | 0.77 | `paintbrush` |
| `0e9362ba-1c57-4a6b-ae08-46cdb8e33752` | 85.35 | paintbrush | right→left | 0.64 | `paint brush` ← fallback |
| `a81b005c-38a2-4913-afe3-55026607a124` | 27.64 | paintbrush | right→left | 0.64 | `paintbrush` |
| `2ff8c772-c1d6-464a-84c8-dcc1532fc5a1` | 203.53 | pencil | left→right | 0.63 | `pencil` |
| `23ffc872-4220-4b48-bcaf-8542a63ee27d` | 84.68 | paintbrush | right→left | 0.61 | `paintbrush` |
| `a81b005c-38a2-4913-afe3-55026607a124` | 107.85 | paintbrush | right→left | 0.54 | `paintbrush` |
| `a81b005c-38a2-4913-afe3-55026607a124` | 290.63 | paintbrush | left→right | 0.44 | `paintbrush` |

Direction balance is **9 right→left, 3 left→right**. If the robot policy needs both
directions evenly, the three left→right ones (`4713085d+118.71`, `2ff8c772+203.53`,
`a81b005c+290.63`) are the scarce ones.

Best four to start from — tool visible in 87–100% of frames, clean single-instance tracks:
`4a2af66c+241.72`, `0e9362ba+128.38`, `ccf8a14a+18.51`, `ccf8a14a+275.67`.

Reproduce all of them with:

```
py sam_ego4d.py ego4d --metadata "C:\Users\40770\Downloads\ego4d.json" ^
  --narrations "C:\Users\40770\Downloads\v2\annotations\narration.json" ^
  --videos "C:\Users\40770\Downloads\v2\clips" --max-clips 100
```

Output is `sam_out\scores\<clip_id>\` with `score.json`, `clip.mp4`, `preview.mp4`, the raw
SAM streams and the COCO RLE masks. `sam_out\index.json` ranks them, best first.

### The 9 that don't work

| clip file | offset | tool visible | why |
|---|---|---|---|
| `2ff8c772` | 226.97 | 0.94 | **regression, see below** |
| `0e9362ba` | 92.29 | 0.55 | `-RBR` — returns to the same hand |
| `a81b005c` | 201.56 | 0.53 | `-L` — right hand never credited |
| `49d65bed` | 22.64 | 0.43 | `-` — "cup of glue" never overlaps either hand |
| `23ffc872` | 25.22 | 0.41 | `-L-L` — right hand never credited |
| `86c35de4` | 175.06 | 0.18 | too sparse to see a handover |
| `a81b005c` | 283.02 | 0.06 | tool tracked in 11 of 180 frames |
| `23ffc872` | 137.96 | 0.06 | same |
| `71889f9e` | 21.69 | 0.00 | SAM found no pencil at all |

Six of these nine are segmentation-limited, not logic-limited — the tool is barely tracked,
so no parameter change can recover them. They are the ones worth re-running at native
resolution (several source clips are 1920 or 2560 wide and we cut at 1280).

---

## 3. Known issues

**A regression I introduced and did not finish fixing.** `2ff8c772+226.97` detected its pass
correctly *before* the retune (held pattern `RBL-`) and does not now (`R-R-R`). Cause:
`HOLD_BOX_PAD` is the default argument of `overlap()`, which is used by **both**
`pick_object_track` ("which of these pencils is the real tool?") and the hold test ("is it
held right now?"). Widening the pad for the second changed the answer to the first, and it
latched onto a different pencil instance. Those are different questions and should not share
a threshold — `pick_object_track` should take its own pad. Net effect of the retune is still
strongly positive (5 → 12), but this one clip is recoverable.

**`match_pass` mis-parses "in his X hand".** For `#C C passes the paintbrush in his right
hand to his left hand`, the second `HAND_TO_HAND` pattern matches the *first* `in … hand` and
reads the destination as `right`, so ground truth comes out as left→right. The detection
(right→left) is correct and the narration label is wrong. This is why `a81b005c+27.64` shows
`agrees_with_narration: false` despite being right. Real agreement is **12/12**, not 11/12.
Fix: require the destination clause to follow a `to`/`into`, or prefer the last match.

**The `hand` prompt over-fires on artwork.** On the watercolor clip it returned 4 hand IDs
with more than two hands in 100% of frames — it segments *painted* hands in the picture.
`assign_sides` just takes the two largest in the lower frame, so it can latch onto a painting.
Watch `extra_hand_frames` in `segmentation_stats`.

**59 of 500 clips have no resolvable parent window** and are addressed as whole videos. They
are harmless (clip UIDs never collide with video UIDs) but unusable. Parsing `fho_main.json`
(2 GB, needs ~10 GB RAM) would likely resolve most of them.

---

## 4. Before committing to GitHub

### Must remove

**The API key.** `sam_pipeline/credentials.py` has `FALLBACK_KEY` set to a live Meta key.
Blank it and use the `MODEL_API_KEY` environment variable. If it has already been committed
in any earlier commit, rotating the key is the only real fix — removing it from the working
tree does not remove it from history.

**All Ego4D-derived video and masks — this is a licensing issue, not just a size issue.**
The Ego4D License Agreement you accepted to download the data prohibits redistribution.
Pushing these to GitHub republishes Ego4D frames:

- `sam_out/` — **139 MB**, including a 2.3 MB `clip.mp4` and a 2.2 MB `preview.mp4` in each
  of 21 score directories
- `test_pass.mp4`, `test_pass2.mp4`, `test_pass2_hi.mp4`, `test_pencil.mp4` — 5.4 MB of cut
  Ego4D footage at the repo root
- `sam_out/scores/*/masks_*.json` — pixel masks derived from Ego4D frames
- `sam_out/scores/*/score.json` — contains Ego4D narration text verbatim and frame
  coordinates. Fine for a private repo; for a public one, treat it as Ego4D data.

### Should remove

- `__pycache__/` — compiled bytecode
- `run21.log`, `rerun.log` — 22 KB of run output
- `sam_out/clip_index.json`, `sam_out/needed_video_uids.txt` — Ego4D-derived metadata

### Safe to commit

`sam_pipeline/`, `sam_ego4d.py`, `work.md`, this file, and a `.gitignore`.

### Suggested `.gitignore`

```
__pycache__/
*.pyc
sam_out/
*.mp4
*.log
.sam31_budget.json
```

Note the repo has **no commits of any of this yet** — `git status` shows everything as
untracked — so adding `.gitignore` before the first `git add` keeps all of it out of history
cleanly.
