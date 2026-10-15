#!/usr/bin/env python3
"""Render a local editorial plan with existing media/audio, then inspect the actual MP4."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitok.config import Settings
from kitok.editing.storyboard import EditorialPlan
from kitok.editing.production import render_editorial_plan
from kitok.editing.quality import inspect_video


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--encoder", choices=["auto","libx264","h264_nvenc"], default="auto")
    parser.add_argument("--compare-to", type=Path, help="Assert decoded audio is identical to this A/B reference")
    args=parser.parse_args(argv)
    settings=Settings()
    plan=EditorialPlan.load(args.plan)
    output=args.output or ROOT/"outputs/longform"/f"{plan.episode_id}_edit.mp4"
    try:
        result=render_editorial_plan(plan,root=ROOT,output=output,settings=settings,
                                     encoder_name=args.encoder,on_stage=lambda s: print(s,flush=True))
        qa=inspect_video(output,output.with_suffix(".qa.json"),settings=settings,comparison=args.compare_to,
                         scene_boundaries=[(s.start+s.end)/2 for s in plan.scenes])
    except (RuntimeError,ValueError,OSError) as error:
        print(f"Editorial render failed: {error}",file=sys.stderr)
        return 1
    print(json.dumps({"output":result["output"],"elapsed_seconds":result["elapsed_seconds"],
                      "rendered":len(result["rendered_scenes"]),"reused":len(result["reused_scenes"]),
                      "qa":str(output.with_suffix(".qa.json")),
                      "audio_comparison":qa.get("comparison")},indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
