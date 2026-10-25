import os
from pathlib import Path
import subprocess
import pytest


@pytest.mark.parametrize('mode', ['1', 'true', 'TRUE', 'yes', 'on', '0'])
def test_start_script_proxy_args(tmp_path, mode):
    python = tmp_path / 'python3'
    python.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    python.chmod(0o700)
    env = {
        **os.environ,
        'PATH': str(tmp_path) + ':' + os.environ['PATH'],
        'S2A_EMBED_MODE': mode,
        'WEBUI_SECRET_KEY': 'test-only',
        'USE_SLIM_DOCKER': 'true',
        'USE_OLLAMA_DOCKER': 'false',
        'USE_CUDA_DOCKER': 'false',
        'SPACE_ID': '',
    }
    script = Path(__file__).resolve().parents[3] / 'start.sh'
    args = ['--forwarded-allow-ips', '192.0.2.1'] if mode == '0' else []
    result = subprocess.run(['bash', str(script), *args], env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert '--root-path' not in result.stdout
    if mode != '0':
        assert '--no-proxy-headers' in result.stdout and '--forwarded-allow-ips' not in result.stdout
    else:
        assert '--forwarded-allow-ips' in result.stdout and '--no-proxy-headers' not in result.stdout
        assert result.stdout.rstrip().endswith('192.0.2.1')  # upstream caller override retains precedence


def test_embed_rejects_root_path(tmp_path):
    script = Path(__file__).resolve().parents[3] / 'start.sh'
    env = {**os.environ, 'S2A_EMBED_MODE': '1', 'WEBUI_SECRET_KEY': 'test-only', 'USE_SLIM_DOCKER': 'true'}
    result = subprocess.run(
        ['bash', str(script), '--root-path', '/_chat'], env=env, capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 64
