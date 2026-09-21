import uvicorn
from ..logging_setup import configure_logging
from ..app_settings import configured

if __name__ == '__main__':
    settings = configured()
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    configure_logging(settings.logs_dir, False)
    uvicorn.run('kitok.api:create_app', factory=True, host='127.0.0.1', port=8000, workers=1)
