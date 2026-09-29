"""Run API regressions against an isolated migrated SQLite DB and artifact directory.

Usage: backend/.venv/Scripts/python.exe scripts/test_security.py [pytest arguments]
No production database, credentials, or artifact directory is used.
"""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

root = Path(__file__).resolve().parents[1]
os.chdir(root)
sys.path[:0] = [str(root), str(root/'backend')]
with TemporaryDirectory(prefix='bci-security-') as scratch:
    directory = Path(scratch)
    os.environ.update(DATABASE_URL='sqlite:///'+(directory/'platform.sqlite').as_posix(),
                      ARTIFACT_DIR=str(directory/'artifacts'), PRODUCTION='false', SECURE_COOKIE='false',
                      OPENAI_API_KEY='', BCI_GUEST_PASSWORD='security-test-guest')
    from alembic.config import Config
    from alembic import command
    config = Config(str(root/'backend/alembic.ini'))
    config.set_main_option('script_location', str(root/'backend/migrations'))
    command.upgrade(config, 'head')
    import pytest
    try:
        code = pytest.main(sys.argv[1:] or ['backend/tests', '-q'])
    finally:
        from app.platform.database import engine
        from app.platform.eog import shutdown
        shutdown()
        engine.dispose()
sys.exit(code)
