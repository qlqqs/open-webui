"""The isolation helper must never change non-embedded administrator semantics."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from open_webui.embed import access


@pytest.mark.parametrize('enabled', [True, False])
@pytest.mark.parametrize('role', ['admin', 'user', 'pending', None])
@pytest.mark.parametrize('shape', ['object', 'dict', 'string'])
def test_resource_admin_is_not_workspace_admin(monkeypatch, enabled, role, shape):
    monkeypatch.setattr(access, 'settings', replace(access.settings, enabled=enabled))
    user = {'object': SimpleNamespace(role=role), 'dict': {'role': role}, 'string': role}[shape]
    assert access.resource_admin(user) == (not enabled and role == 'admin')


@pytest.mark.parametrize('enabled', [True, False])
@pytest.mark.parametrize('missing', ['generic', 'Calendar not found', 'Event not found'])
def test_private_ids_are_indistinguishable(monkeypatch, enabled, missing):
    monkeypatch.setattr(access, 'settings', replace(access.settings, enabled=enabled))
    error = access.private_denied(403, 'denied', missing=missing)
    assert error.status_code == (404 if enabled else 403)
    if enabled and missing != 'generic':
        assert error.detail == missing
    elif not enabled:
        assert error.detail == 'denied'


@pytest.mark.parametrize('document', ['file:abc', 'random', 'note:', 'note:abc:forged', '', None])
def test_no_unprotected_document_rooms(monkeypatch, document):
    monkeypatch.setattr(access, 'settings', replace(access.settings, enabled=True))
    assert not access.valid_document_id(document)
    assert access.valid_document_id('note:abc')
    monkeypatch.setattr(access, 'settings', replace(access.settings, enabled=False))
    assert access.valid_document_id(document)


@pytest.mark.parametrize(
    'chat_id,session_id',
    [
        ('temporary:foreign', None),
        ('local:foreign', None),
        ('channel:foreign', None),
        (None, 'foreign'),
        ('temporary:', None),
    ],
)
def test_socket_address_is_private(monkeypatch, chat_id, session_id):
    from fastapi import HTTPException

    monkeypatch.setattr(access, 'settings', replace(access.settings, enabled=True))
    with pytest.raises(HTTPException) as exc:
        access.check_chat_session(chat_id, session_id, 'admin', lambda sid: None)
    assert exc.value.status_code == 404
    access.check_chat_session('temporary:mine', 'mine', 'admin', lambda sid: 'admin')
    monkeypatch.setattr(access, 'settings', replace(access.settings, enabled=False))
    access.check_chat_session(chat_id, session_id, 'admin', lambda sid: None)
