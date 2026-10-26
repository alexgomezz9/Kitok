#!/usr/bin/env python3
"""Remove reviewed synthesis artifacts in a new episode; no providers/render."""
import argparse
import subprocess

from kitok.config import PROJECT_ROOT, Settings
from kitok.youtube_stickman_es.audio_cuts import repair_audio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episode')
    parser.add_argument('--output', required=True, help='New episode path inside the workspace')
    parser.add_argument('--cut', action='append', required=True, help='Reviewed gap START:END in seconds; repeat as needed')
    parser.add_argument('--reviewer', required=True)
    parser.add_argument('--tempo', type=float, default=1.0,
                        help='Optional pitch-preserving tempo 0.9–1.1; real word times transform with the audio')
    parser.add_argument('--reason', default='Operator confirmed non-speech synthesis artifacts in these gaps')
    args = parser.parse_args()
    from pathlib import Path
    try:
        cuts = [tuple(map(float, value.split(':'))) for value in args.cut]
        if any(len(cut) != 2 for cut in cuts):
            raise ValueError('Each cut must be START:END')
        target = repair_audio(PROJECT_ROOT, Path(args.episode), args.output, cuts,
                              settings=Settings(), reviewer=args.reviewer, tempo=args.tempo, reason=args.reason)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(2, str(error)+'\n')
    print(f'Audio repaired in {target.relative_to(PROJECT_ROOT)}; originals preserved. Run prepare --reuse-images, not --generate-voice.')


if __name__ == '__main__':
    main()
