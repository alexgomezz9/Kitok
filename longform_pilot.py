from pathlib import Path
import json
import time

from kitok.config import Settings, PROJECT_ROOT
from kitok.mpt_client import (
    MPTClient,
    TASK_STATE_COMPLETE,
    TASK_STATE_FAILED,
)
from kitok.models import ContentItem

s = Settings()

preset = json.loads(
    (PROJECT_ROOT / "presets" / "mpt_default.json").read_text(encoding="utf-8")
)

preset.update({
    "video_aspect": "16:9",
    "video_fit_mode": "cover",
    "video_concat_mode": "sequential",
    "video_transition_mode": None,
    "video_clip_duration": 5,
    "video_clip_speed": 1.0,
    "match_materials_to_script": True,
    "video_count": 1,
    "video_source": "pexels",
    "video_language": "en",
    "voice_name": "en-US-GuyNeural",
    "voice_volume": 1.0,
    "voice_rate": 1.0,
    "bgm_type": "",
    "bgm_file": "",
    "bgm_volume": 0.0,
    "subtitle_enabled": False,
})

script = Path("pilot_script.txt").read_text(encoding="utf-8").strip()

item = ContentItem(
    id="pilot_airline_overbooking_001",
    subject="Why Airlines Sell More Tickets Than They Have Seats",
    script=script,
    keywords=[
        "airport passengers",
        "airplane boarding",
        "airport departure board",
        "airline check in",
        "airplane cabin",
        "airport terminal",
        "passenger waiting airport",
        "airplane taking off",
        "business traveler airport",
        "airline ticket",
        "airport gate",
        "commercial airplane",
    ],
    caption="",
    youtube_title="Why Airlines Sell More Tickets Than They Have Seats",
    platforms=["youtube"],
    content_format="explainer",
    visual_profile="pexels",
    schedule_enabled=False,
)

client = MPTClient(
    s.mpt_base_url,
    s.mpt_api_key,
    timeout_seconds=s.mpt_request_timeout_seconds,
    retry_attempts=s.http_retry_attempts,
    retry_base_seconds=s.http_retry_base_seconds,
)

try:
    print("Submitting long-form pilot...")
    task_id = client.submit_video(item, preset)
    print("Task:", task_id)

    while True:
        task = client.get_task(task_id)

        print(
            f"state={task.state} "
            f"progress={task.progress} "
            f"videos={len(task.videos)}"
        )

        if task.state == TASK_STATE_COMPLETE:
            if not task.videos:
                raise RuntimeError("MPT completed but returned no video")

            out = PROJECT_ROOT / "outputs" / "longform"
            out.mkdir(parents=True, exist_ok=True)

            target = out / "pilot_airline_overbooking_001.mp4"

            print("Downloading...")
            client.download_artifact(task.videos[0], target)

            print("DONE:", target.resolve())
            break

        if task.state == TASK_STATE_FAILED:
            raise RuntimeError(
                f"MPT failed: {task.error or task.failed_stage or task.raw}"
            )

        time.sleep(5)

finally:
    client.close()
