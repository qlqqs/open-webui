import os
from pathlib import Path
import subprocess
import sys


def test_real_backend_gateway_proxy_and_upstream_mode():
    script = Path(__file__).with_name('smoke') / 'run.py'
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[3])}
    result = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"status": "PASS"' in result.stdout


def test_real_hook_functions_and_socket_revalidation(tmp_path):
    script = Path(__file__).with_name('smoke') / 'hook_checks.py'
    env = {k: v for k, v in os.environ.items() if not k.lower().endswith('_proxy')}
    env.update(
        {
            'PYTHONPATH': str(Path(__file__).resolve().parents[3]),
            'USE_SLIM_DOCKER': 'true',
            'S2A_EMBED_MODE': '1',
            'S2A_GATEWAY_URL': 'http://127.0.0.1:28201',
            'S2A_TRUSTED_PROXY_CIDRS': '127.0.0.1/32',
            'DATA_DIR': str(tmp_path),
            'STATIC_DIR': str(tmp_path / 'static'),
            'WEBUI_SECRET_KEY': 'isolated-hook-tests-secret',
            'S2A_SMOKE_NETWORK_LOG': str(tmp_path / 'network.jsonl'),
        }
    )
    result = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'HOOK_CHECKS_PASS' in result.stdout
    assert not (tmp_path / 'network.jsonl').exists(), 'Hook tests attempted network access'
