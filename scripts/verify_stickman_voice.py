#!/usr/bin/env python3
"""Compare existing voice with its script using independent ASR; never synthesize."""
import argparse
import json
from pathlib import Path

from kitok.config import PROJECT_ROOT, Settings
from kitok.youtube_stickman_es.files import digest, episode_lock, episode_path, write
from kitok.youtube_stickman_es.voice_fidelity import verify_voice


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episode', type=Path)
    parser.add_argument('--transcribe', action='store_true', help='Run existing local CPU/int8 ASR if no saved result; never uploads or synthesizes')
    parser.add_argument('--cut-insertions', action='store_true', help='Remove safely anchored insertions in a new PCM copy and recognize again; blocks montage if differences remain')
    parser.add_argument('--local-python', type=Path, help='Existing Python with faster-whisper; or LOCAL_ASR_PYTHON setting')
    parser.add_argument('--local-model', type=Path, help='Existing local CTranslate2 Whisper model; or LOCAL_ASR_MODEL setting')
    parser.add_argument('--import-asr', type=Path, help='Saved local ASR JSON including exact audio_sha256; runtime/model must identify provenance')
    parser.add_argument('--accept-differences', action='store_true', help='Record actual review of every difference, without editing audio')
    parser.add_argument('--reviewer')
    parser.add_argument('--reason')
    args = parser.parse_args(argv)
    if args.accept_differences and not (args.reviewer and args.reason):
        parser.error('--accept-differences requires --reviewer and --reason')
    try:
        episode = episode_path(PROJECT_ROOT, args.episode)
        with episode_lock(episode):
            if args.cut_insertions:
                if args.accept_differences or args.import_asr:
                    parser.error('--cut-insertions cannot accept differences or replace recognition evidence')
                from kitok.youtube_stickman_es.audio import prepare_narration
                from kitok.youtube_stickman_es.voice_cleaning import clean_narration
                settings = Settings()
                if args.local_python:
                    settings.local_asr_python = args.local_python
                if args.local_model:
                    settings.local_asr_model = args.local_model
                raw = prepare_narration(episode, root=PROJECT_ROOT, settings=settings, generate=False)
                report = clean_narration(episode, settings=settings, raw=raw, require_ready=False)
                print(json.dumps(report, ensure_ascii=False, indent=2))
                return 0 if report.get('status') == 'ready' or 'duration' in report else 2
            report = verify_voice(episode, settings=Settings(), transcribe=args.transcribe,
                local_python=args.local_python, local_model=args.local_model, imported_result=args.import_asr)
            if args.accept_differences:
                path = Path(report['report_path'])
                write(path.parent / 'review.json', {'decision': 'accept_asr_differences',
                    'report_sha256': digest(path), 'reviewer': args.reviewer, 'reason': args.reason})
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
