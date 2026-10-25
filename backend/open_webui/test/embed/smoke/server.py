"""Smoke-only uvicorn entrypoint: fail before *any* non-loopback network IO."""

import json
import os
import sys


def audit(event, args):
    address = None
    if event == 'socket.connect':
        address = args[1]
    elif event == 'socket.getaddrinfo':
        address = (args[0], args[1])
    if not isinstance(address, tuple):
        return
    host, port = address[:2]
    allowed = host == '127.0.0.1' and isinstance(port, int) and 28200 <= port <= 28219
    with open(os.environ['S2A_SMOKE_NETWORK_LOG'], 'a') as log:
        log.write(json.dumps({'event': event, 'host': host, 'port': port, 'allowed': allowed}) + '\n')
    if not allowed:
        raise RuntimeError('Smoke network guard rejected a non-loopback destination')


if __name__ == '__main__':
    sys.addaudithook(audit)
    import uvicorn

    uvicorn.run('open_webui.main:app', host='127.0.0.1', port=28200, proxy_headers=False, log_level='warning')
