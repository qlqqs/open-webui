"""Exercise the conditional initialization against an isolated SQLite DB."""
import os
import subprocess
import sys
from pathlib import Path


def test_conditional_initialization_preserves_manual_settings(tmp_path):
    code = r'''
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import insert, select
from open_webui.models.users import User
from open_webui.embed.workbench import initialize_settings

async def main():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
    session = async_sessionmaker(engine, expire_on_commit=False)
    async with session() as db:
        await db.execute(insert(User).values(id='a', name='A', email='a@test.invalid', role='user',
            profile_image_url='/user.png', created_at=1, updated_at=1, last_active_at=1, settings={}))
        await db.commit()
        patch={'ui': {'sub2api': {'key_id': 3}, 'models': ['gpt-6.1-sol']}}
        first=await initialize_settings('a',patch,db)
        assert first.settings.ui['sub2api']['key_id']==3
        assert first.settings.ui['sub2api_initialized'] is True
        second=await initialize_settings('a',{'ui': {'sub2api': {'key_id': 99}}},db)
        assert second.settings.ui['sub2api']['key_id']==3
        row=await db.get(User,'a')
        row.settings={'ui': {'sub2api': {'key_id': None}, 'sub2api_initialized': True}}
        await db.commit()
        cleared=await initialize_settings('a',patch,db)
        assert cleared.settings.ui['sub2api']['key_id'] is None
    await engine.dispose()
asyncio.run(main())
'''
    backend = Path(__file__).resolve().parents[3]
    env = {**os.environ, 'PYTHONPATH': str(backend), 'DATA_DIR': str(tmp_path),
           'DATABASE_URL': f'sqlite:///{tmp_path}/test.db', 'OFFLINE_MODE': 'true',
           'ENABLE_VERSION_UPDATE_CHECK': 'false', 'WEBUI_SECRET_KEY': 'isolated-workbench-test-secret-key'}
    result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
