"""Mode: episode (robot overhead video -> the label's vision section)."""

from __future__ import annotations

import json
import sys

from sam_pipeline.analysis import analyse
from sam_pipeline.budget import Budget
from sam_pipeline.config import MODEL, object_fallbacks
from sam_pipeline.credentials import api_key
from sam_pipeline.pipeline import segment_video
from sam_pipeline.preview import render_preview
from sam_pipeline.sam_client import SamClient
from sam_pipeline.video import cut_clip, probe


def run_episode(args, budget: Budget) -> None:
    video = args.video
    w, h, fps, n = probe(video)
    outdir = args.out / "episodes" / f"{args.episode}"
    outdir.mkdir(parents=True, exist_ok=True)
    # SAM wants H.264; robot recordings may be AV1/VP9 (LeRobot default), so re-encode once
    sam_video = outdir / "overhead_h264.mp4"
    if not sam_video.exists():
        cut_clip(video, sam_video, 0, n / fps, w, fps)
    client = SamClient(api_key(), args.base_url)
    results = segment_video(client, budget, sam_video, {"holder": args.holder_prompt, "object": args.object},
                            outdir, fps, n, w, h, not args.no_rle, f"episode {args.episode}",
                            fallbacks={"object": object_fallbacks(args.object)},
                            max_attempts=args.object_attempts, retry_empty=args.retry_empty)
    if results is None:
        sys.exit(1)
    a = analyse(results, None, n, fps, w, h, holder_name="gripper")
    objects, events, notes = a.objects, a.events, a.notes
    # contract: vision.objects lists the task objects; holders are robot grippers, kept out
    vision = {"model": MODEL, "objects": [objects[0]], "events": events}
    (outdir / "vision.json").write_text(json.dumps(vision, indent=2))
    (outdir / "segmentation_stats.json").write_text(json.dumps(
        {**a.stats, "object_prompt": a.object_prompt,
         "object_prompt_fallback": a.object_prompt != args.object}, indent=2))
    if not args.no_preview:
        render_preview(sam_video, outdir / "preview.mp4", results, a, w, h, fps)
        print(f"preview: {outdir / 'preview.mp4'}")
    print(json.dumps(vision, indent=2))
    if notes:
        print("parser notes:", *notes[:10], sep="\n  ")
    if args.send:
        from harness import robot   # Vlad's client
        final = robot.episode_label(args.episode, "vision", vision)
        print("sent to robotd:", final)
