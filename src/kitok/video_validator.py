from __future__ import annotations
import json, shutil, subprocess
from pathlib import Path
from .models import ValidationResult

class VideoValidator:
    def __init__(self, ffprobe_binary="ffprobe", min_seconds=5.0, max_seconds=60.0,
                 min_vertical_width=540, min_vertical_height=960):
        self.ffprobe_binary=ffprobe_binary
        self.min_seconds=min_seconds
        self.max_seconds=max_seconds
        self.min_vertical_width=min_vertical_width
        self.min_vertical_height=min_vertical_height

    def ffprobe_available(self): return shutil.which(self.ffprobe_binary) is not None

    def validate(self,path:Path)->ValidationResult:
        errors=[]; warnings=[]
        if not path.exists(): return ValidationResult(ok=False,errors=["file does not exist"])
        if path.stat().st_size<=0: return ValidationResult(ok=False,errors=["file is empty"])
        if not self.ffprobe_available():
            return ValidationResult(ok=False,errors=[f"{self.ffprobe_binary!r} not found"])
        cmd=[self.ffprobe_binary,"-v","error","-show_streams","-show_format","-of","json",str(path)]
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
        except Exception as e:
            return ValidationResult(ok=False,errors=[f"ffprobe failed: {e}"])
        if p.returncode!=0:
            return ValidationResult(ok=False,errors=[f"ffprobe could not read video: {p.stderr[:1000]}"])
        try: info=json.loads(p.stdout)
        except json.JSONDecodeError as e:
            return ValidationResult(ok=False,errors=[f"invalid ffprobe JSON: {e}"])

        streams=info.get("streams",[])
        vs=[s for s in streams if s.get("codec_type")=="video"]
        aus=[s for s in streams if s.get("codec_type")=="audio"]
        if not vs: errors.append("no video stream")
        if not aus: errors.append("no audio stream")

        duration=None
        try: duration=float(info.get("format",{}).get("duration"))
        except (TypeError,ValueError): warnings.append("could not parse duration")
        if duration is not None:
            if duration<self.min_seconds: errors.append(f"duration {duration:.2f}s below minimum")
            if duration>self.max_seconds: errors.append(f"duration {duration:.2f}s above maximum")

        width=height=None; vcodec=None
        if vs:
            width=int(vs[0].get("width") or 0); height=int(vs[0].get("height") or 0)
            vcodec=vs[0].get("codec_name")
            if width<=0 or height<=0: errors.append("invalid video dimensions")
            elif height<=width: errors.append(f"not vertical: {width}x{height}")
            elif width<self.min_vertical_width or height<self.min_vertical_height:
                warnings.append(f"low-ish vertical resolution: {width}x{height}")

        acodec=aus[0].get("codec_name") if aus else None
        return ValidationResult(ok=not errors,errors=errors,warnings=warnings,duration=duration,
                                width=width,height=height,video_codec=vcodec,audio_codec=acodec)
