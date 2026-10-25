"""Real HTTP/socket R3 regressions; called by the local-only smoke harness."""

import asyncio
import json
import time
import uuid


async def check_isolation(client, auth, tokens, harness, socket_connect, chat_id):
    checks = 0
    marker = 'PRIVATE-R3-' + uuid.uuid4().hex

    async def ok(method, path, uid=1, **kwargs):
        nonlocal checks
        response = await client.request(method, path, headers=auth(uid), **kwargs)
        assert response.status_code == 200, (method, path, response.status_code, response.text)
        checks += 1
        return response.json()

    async def same_as_absent(method, template, rid, **kwargs):
        nonlocal checks
        for uid in (2, 3):
            other = await client.request(method, template.format(rid), headers=auth(uid), **kwargs)
            missing = await client.request(method, template.format(str(uuid.uuid4())), headers=auth(uid), **kwargs)
            assert other.status_code == missing.status_code and other.status_code in (401, 403, 404), (
                method,
                template,
                uid,
                other.status_code,
                other.text,
                missing.status_code,
                missing.text,
            )
            assert other.json() == missing.json(), (method, template, uid, other.text, missing.text)
            checks += 1

    note = await ok(
        'POST', '/api/v1/notes/create', json={'title': marker, 'data': {'content': {'md': marker}}, 'access_grants': []}
    )
    folder = await ok('POST', '/api/v1/folders/', json={'name': marker, 'data': {'system_prompt': marker}})
    calendar = await ok('POST', '/api/v1/calendars/create', json={'name': marker, 'access_grants': []})
    event = await ok(
        'POST',
        '/api/v1/calendars/events/create',
        json={
            'calendar_id': calendar['id'],
            'title': marker,
            'start_at': time.time_ns(),
        },
    )
    file = await ok(
        'POST',
        '/api/v1/files/?process_in_background=false',
        files={'file': (marker + '.txt', marker.encode(), 'text/plain')},
    )
    await ok('POST', f'/api/v1/chats/{chat_id}/tags', json={'name': marker})
    internal = await ok('GET', f'/api/v1/notes/{note["id"]}/chat')

    for cid in (chat_id, internal['id']):
        for method, suffix, body in (
            ('GET', '', None),
            ('POST', '', {'chat': {'title': 'forged'}}),
            ('GET', '/tags', None),
            ('POST', '/tags', {'name': 'forged'}),
            ('DELETE', '/tags', {'name': marker}),
            ('POST', '/folder', {'folder_id': folder['id']}),
            ('POST', '/clone', {}),
            ('DELETE', '', None),
        ):
            await same_as_absent(
                method, '/api/v1/chats/{}' + suffix, cid, **({'json': body} if body is not None else {})
            )
    for method, suffix, body in (
        ('GET', '', None),
        ('GET', '/content', None),
        ('GET', '/content/html', None),
        ('GET', '/content/secret.txt', None),
        ('GET', '/data/content', None),
        ('GET', '/process/status', None),
        ('POST', '/rename', {'filename': 'forged.txt'}),
        ('POST', '/data/content/update', {'content': 'forged'}),
        ('DELETE', '', None),
    ):
        await same_as_absent(
            method, '/api/v1/files/{}' + suffix, file['id'], **({'json': body} if body is not None else {})
        )
    for method, suffix, body in (
        ('GET', '', None),
        ('GET', '/chat', None),
        ('GET', '/chats', None),
        ('POST', '/chat', None),
        ('POST', '/update', {'title': 'forged'}),
        ('POST', '/access/update', {'access_grants': []}),
        ('POST', '/pin', None),
        ('DELETE', '/delete', None),
    ):
        await same_as_absent(
            method, '/api/v1/notes/{}' + suffix, note['id'], **({'json': body} if body is not None else {})
        )
    for base, rid in (('/api/v1/calendars/{}', calendar['id']), ('/api/v1/calendars/events/{}', event['id'])):
        for method, suffix, body in (
            ('GET', '', None),
            ('POST', '/update', {'name': 'forged', 'title': 'forged'}),
            ('DELETE', '/delete', None),
        ):
            await same_as_absent(method, base + suffix, rid, **({'json': body} if body is not None else {}))
    for method, suffix, body in (
        ('GET', '', None),
        ('POST', '/update', {'name': 'forged'}),
        ('POST', '/update/expanded', {'is_expanded': True}),
        ('POST', '/access/update', {'access_grants': []}),
        ('GET', '/shared/chats', None),
        ('POST', '/read', None),
        ('DELETE', '', None),
    ):
        await same_as_absent(
            method, '/api/v1/folders/{}' + suffix, folder['id'], **({'json': body} if body is not None else {})
        )

    # Lists, search, exports and counts are scoped, regardless of administrator role.
    for uid in (2, 3):
        for path in (
            '/api/v1/chats/',
            '/api/v1/chats/search?text=' + marker,
            '/api/v1/chats/all',
            '/api/v1/chats/all/tags',
            '/api/v1/notes/',
            '/api/v1/notes/search?query=' + marker,
            '/api/v1/files/',
            '/api/v1/files/search?filename=' + marker + '*',
            '/api/v1/folders/',
            '/api/v1/folders/shared',
            '/api/v1/calendars/',
            '/api/v1/calendars/events/search?query=' + marker,
            '/api/v1/calendars/events?start=2020-01-01&end=2030-01-01&calendar_ids=' + calendar['id'],
            '/api/v1/search?q=' + marker,
        ):
            response = await client.get(path, headers=auth(uid))
            assert response.status_code in (200, 404), (path, response.status_code, response.text)
            assert (
                marker not in response.text and note['id'] not in response.text and file['id'] not in response.text
            ), (uid, path, response.text)
            checks += 1
        if uid == 3:
            assert await ok('GET', '/api/v1/files/count', uid) == 0

    # Cannot launder another user's file/note through a managed Workspace model.
    for kind, rid in (('file', file['id']), ('note', note['id'])):
        response = await client.post(
            '/api/v1/models/create',
            headers=auth(3),
            json={
                'id': 'forged-' + kind,
                'base_model_id': 'common',
                'name': 'forged',
                'params': {},
                'meta': {'knowledge': [{'type': kind, 'id': rid}]},
                'access_grants': [],
            },
        )
        assert response.status_code == 404, (kind, response.status_code, response.text)
        checks += 1

    # Retrieval via raw chat attachment and folder context must not disclose private text.
    for kind, rid in (('file', file['id']), ('note', note['id']), ('chat', internal['id']), ('folder', folder['id'])):
        before = len(harness.records)
        response = await client.post(
            '/api/chat/completions',
            headers=auth(3),
            json={
                'model': 'common',
                'messages': [{'role': 'user', 'content': 'summarize'}],
                'stream': False,
                'params': {'function_calling': 'legacy'},
                'files': [{'type': kind, 'id': rid, 'context': 'full'}],
            },
        )
        assert response.status_code in (200, 400, 403, 404), response.text
        assert marker not in json.dumps(harness.records[before:]), (kind, harness.records[before:])
        checks += 1

    # Socket joins and pushes: administrator cannot join private chats, internal chats or notes.
    admin_socket = await socket_connect(3)
    owner_socket = await socket_connect(1)
    # Global tasks are blocked; per-chat tasks and temporary socket IDs are owner checked.
    for method, path in (('GET', '/api/tasks'), ('POST', '/api/tasks/stop/foreign')):
        response = await client.request(method, path, headers=auth(3))
        assert response.status_code == 403
        checks += 1
    for cid in (chat_id, internal['id'], 'temporary:' + owner_socket.get_sid(), 'local:' + owner_socket.get_sid()):
        assert await ok('GET', '/api/tasks/chat/' + cid, 3) == {'task_ids': []}
        await same_as_absent('POST', '/api/tasks/chat/{}/stop', cid)
    for payload in (
        {'session_id': owner_socket.get_sid()},
        {'chat_id': 'temporary:' + owner_socket.get_sid()},
        {'chat_id': 'local:' + owner_socket.get_sid()},
        {'chat_id': 'channel:foreign'},
    ):
        response = await client.post(
            '/api/chat/completions',
            headers=auth(3),
            json={
                'model': 'common',
                'messages': [{'role': 'user', 'content': 'forged callback'}],
                'stream': False,
                **payload,
            },
        )
        assert response.status_code == 404, response.text
        checks += 1
    note_events, doc_states, chat_events = [], [], []
    admin_socket.on('events:note', lambda data: note_events.append(data))
    admin_socket.on('ydoc:document:state', lambda data: doc_states.append(data))
    admin_socket.on('events', lambda data: chat_events.append(data))
    for cid in (chat_id, internal['id'], str(uuid.uuid4())):
        result = await admin_socket.call('events:chat', {'chat_id': cid, 'data': {'type': 'join'}})
        assert result is False, result
        checks += 1
    for nid in (note['id'], str(uuid.uuid4())):
        await admin_socket.call('join-note', {'note_id': nid, 'auth': {'token': tokens[3]}})
        await admin_socket.call('ydoc:document:join', {'document_id': 'note:' + nid})
        await admin_socket.call('ydoc:document:join', {'document_id': 'note_' + nid})
    await ok('POST', f'/api/v1/notes/{note["id"]}/update', json={'title': marker + '-updated'})
    # Publish an owner typing event to the chat room; rejected admin must not receive it.
    assert await owner_socket.call('events:chat', {'chat_id': chat_id, 'data': {'type': 'join'}})
    assert await owner_socket.call(
        'events:chat', {'chat_id': chat_id, 'data': {'type': 'typing', 'data': {'typing': True}}}
    )
    await asyncio.sleep(0.1)
    assert not note_events and not doc_states and not chat_events, (note_events, doc_states, chat_events)
    checks += 1

    # Existing explicit note read/write grants still work for admins; revocation removes rooms.
    admin = await ok('GET', '/api/v1/auths/', 3)
    grants = [{'principal_type': 'user', 'principal_id': admin['id'], 'permission': p} for p in ('read', 'write')]
    await ok('POST', f'/api/v1/notes/{note["id"]}/access/update', json={'access_grants': grants})
    shared = await ok('GET', f'/api/v1/notes/{note["id"]}', 3)
    assert shared['write_access'] and marker in json.dumps(shared)
    await admin_socket.call('join-note', {'note_id': note['id'], 'auth': {'token': tokens[3]}})
    await admin_socket.call('ydoc:document:join', {'document_id': 'note:' + note['id']})
    assert doc_states, 'Explicitly shared note must be joinable'
    await ok('POST', f'/api/v1/notes/{note["id"]}/update', 3, json={'title': marker + '-shared'})
    await asyncio.sleep(0.1)
    assert note_events
    await ok('POST', f'/api/v1/notes/{note["id"]}/access/update', json={'access_grants': []})
    note_events.clear()
    doc_states.clear()
    await ok('POST', f'/api/v1/notes/{note["id"]}/update', json={'title': marker})
    await admin_socket.call('ydoc:document:state', {'document_id': 'note:' + note['id']})
    await asyncio.sleep(0.1)
    assert not note_events and not doc_states
    await same_as_absent('GET', '/api/v1/notes/{}', note['id'])
    checks += 1

    # Private note attachments can be shared read-only; revoked permission is not sticky.
    await ok(
        'POST',
        f'/api/v1/notes/{note["id"]}/update',
        json={
            'title': marker,
            'data': {'files': [{'type': 'file', 'id': file['id']}]},
            'access_grants': grants[:1],
        },
    )
    assert marker in json.dumps(await ok('GET', f'/api/v1/files/{file["id"]}', 3))
    await same_as_absent('DELETE', '/api/v1/files/{}', file['id'])
    await ok('POST', f'/api/v1/notes/{note["id"]}/access/update', json={'access_grants': []})
    await same_as_absent('GET', '/api/v1/files/{}', file['id'])

    # Explicit read-only calendar/folder sharing remains usable, without admin write escalation.
    await ok('POST', f'/api/v1/calendars/{calendar["id"]}/update', json={'access_grants': grants[:1]})
    await ok('GET', f'/api/v1/calendars/events/{event["id"]}', 3)
    response = await client.post(
        f'/api/v1/calendars/events/{event["id"]}/update', headers=auth(3), json={'title': 'forged'}
    )
    assert response.status_code == 404, response.text
    await ok('POST', f'/api/v1/calendars/{calendar["id"]}/update', json={'access_grants': []})
    await ok('POST', f'/api/v1/folders/{folder["id"]}/access/update', json={'access_grants': grants[:1]})
    shared_folder = await ok('GET', f'/api/v1/folders/{folder["id"]}', 3)
    assert not shared_folder['write_access']
    await same_as_absent('POST', '/api/v1/folders/{}/update', folder['id'], json={'name': 'forged'})
    await same_as_absent('DELETE', '/api/v1/folders/{}', folder['id'])
    await ok('POST', f'/api/v1/folders/{folder["id"]}/access/update', json={'access_grants': []})
    # Rejected/revoked document members cannot write by submitting Yjs snapshot data.
    await admin_socket.call(
        'ydoc:document:update',
        {
            'document_id': 'note:' + note['id'],
            'data': {'content': {'md': 'forged private note'}},
        },
    )
    await asyncio.sleep(0.6)
    unchanged = await ok('GET', f'/api/v1/notes/{note["id"]}')
    assert 'forged private note' not in json.dumps(unchanged)
    checks += 2

    # All forbidden attempts left the owner's data intact.
    for path in (
        f'/api/v1/chats/{chat_id}',
        f'/api/v1/notes/{note["id"]}',
        f'/api/v1/files/{file["id"]}',
        f'/api/v1/calendars/events/{event["id"]}',
        f'/api/v1/folders/{folder["id"]}',
    ):
        await ok('GET', path)
    await admin_socket.disconnect()
    await owner_socket.disconnect()
    return checks
