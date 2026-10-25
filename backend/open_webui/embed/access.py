"""Embedded administrators manage Workspace, not other users' private data.

Do not replace the authenticated role globally: that would break Workspace ACLs.
Only user-resource bypass sites call this helper. Owner/explicit grant checks stay
in upstream code, including read-only versus write sharing semantics.
"""

from open_webui.embed.settings import settings


def resource_admin(user):
    """Preserve upstream admin bypass only when embedding is disabled."""
    role = (
        user if isinstance(user, str) else (user.get('role') if isinstance(user, dict) else getattr(user, 'role', None))
    )
    return not settings.enabled and role == 'admin'


def private_denied(status_code=403, detail=None, *, missing='generic'):
    """Do not disclose private IDs through different absent/denied responses."""
    from fastapi import HTTPException
    from open_webui.constants import ERROR_MESSAGES

    if settings.enabled:
        return HTTPException(404, ERROR_MESSAGES.NOT_FOUND if missing == 'generic' else missing)
    return HTTPException(status_code, detail)


async def check_model_attachments(items, user, db):
    """Workspace authors cannot launder somebody else's notes/files into a model."""
    if not settings.enabled:
        return
    from fastapi import HTTPException
    from open_webui.models.notes import Notes
    from open_webui.models.access_grants import AccessGrants
    from open_webui.utils.access_control.files import has_access_to_file

    for item in items or []:
        if not isinstance(item, dict) or not item.get('id'):
            continue
        kind, rid = item.get('type'), item['id']
        if kind == 'file':
            allowed = await has_access_to_file(rid, 'read', user, db=db)
        elif kind == 'note':
            note = await Notes.get_note_by_id(rid, db=db)
            allowed = note and (
                note.user_id == user.id
                or await AccessGrants.has_access(
                    user_id=user.id, resource_type='note', resource_id=rid, permission='read', db=db
                )
            )
        elif kind == 'collection':
            allowed = False  # Knowledge is disabled by the embedded product contract.
        else:
            continue
        if not allowed:
            raise HTTPException(404, 'Referenced attachment not found')


def valid_document_id(document_id):
    """Only canonical note rooms exist in embed mode, never arbitrary Yjs rooms."""
    if not settings.enabled:
        return True
    return (
        isinstance(document_id, str)
        and document_id.startswith('note:')
        and bool(document_id[5:])
        and ':' not in document_id[5:]
    )


def tool_denied(original, missing):
    """Match missing-resource tool replies too (not just HTTP status codes)."""
    return missing if settings.enabled else original


def check_chat_session(chat_id, session_id, user_id, owner_lookup):
    """Bind temporary chat IDs and event callbacks to the authenticated user."""
    if not settings.enabled:
        return
    from fastapi import HTTPException
    from open_webui.constants import ERROR_MESSAGES
    from open_webui.utils.chat_id import get_temporary_chat_session_id

    chat_id = chat_id or ''
    if chat_id.startswith('channel:'):
        raise HTTPException(404, ERROR_MESSAGES.NOT_FOUND)
    temporary_sid = get_temporary_chat_session_id(chat_id)
    for sid in (session_id, temporary_sid):
        if sid is not None and owner_lookup(sid) != user_id:
            raise HTTPException(404, ERROR_MESSAGES.NOT_FOUND)
