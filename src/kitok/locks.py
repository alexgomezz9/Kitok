"""Cross-process generation exclusion; the lock file is never deleted."""
from contextlib import contextmanager
import fcntl


class GenerationBusy(RuntimeError):
    pass


@contextmanager
def generation_lock(settings, content_id):
    folder = settings.state_path.parent / 'jobs'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / f'{content_id}.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise GenerationBusy('This video is already being generated') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
