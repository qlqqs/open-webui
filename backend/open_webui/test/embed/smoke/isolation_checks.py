"""Real model/helper/tool regression checks, using bounded DB stubs and no IO."""

from dataclasses import replace
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from open_webui.embed import access
from open_webui.models.access_grants import AccessGrants
from open_webui.models.calendar import Calendars, CalendarEvents
from open_webui.models.chats import Chats, ChatModel
from open_webui.models.files import Files
from open_webui.models.groups import Groups
from open_webui.models.notes import Notes
from open_webui.models.shared_chats import SharedChats
from open_webui.models.users import UserModel
from open_webui.routers import calendar, files
from open_webui.tools import builtin
from open_webui.utils.access_control import files as file_access


async def run():
    user = UserModel(
        id='admin',
        email='u3@sub2api.internal',
        name='Admin',
        role='admin',
        created_at=1,
        updated_at=1,
        last_active_at=1,
    )
    cal = SimpleNamespace(id='calendar', user_id='owner')
    note = SimpleNamespace(id='note', user_id='owner', data={'content': {'md': 'PRIVATE'}}, title='PRIVATE')
    file = SimpleNamespace(id='file', user_id='owner', data={'content': 'PRIVATE'}, filename='private.txt')
    chat = ChatModel(
        id='chat',
        user_id='owner',
        title='PRIVATE',
        chat={},
        meta={'internal': True, 'type': 'note'},
        created_at=1,
        updated_at=1,
    )
    with (
        patch.object(Groups, 'get_groups_by_member_id', AsyncMock(return_value=[])),
        patch.object(AccessGrants, 'has_access', AsyncMock(return_value=False)) as grants,
        patch.object(SharedChats, 'get_by_chat_id', AsyncMock(return_value=None)),
        patch.object(Calendars, 'get_calendar_by_id', AsyncMock(return_value=cal)) as calendar_lookup,
        patch.object(Notes, 'get_note_by_id', AsyncMock(return_value=note)) as note_lookup,
        patch.object(Files, 'get_file_by_id', AsyncMock(return_value=file)) as file_lookup,
        patch.object(file_access, 'has_access_to_file', AsyncMock(return_value=False)),
    ):
        assert await Chats.get_accessible_chat_by_id('chat', user, chat=chat) is None
        assert await builtin._has_read_access_to_file(file, user.model_dump()) is False
        for helper, args, lookup, missing in (
            (builtin.view_note, {'note_id': 'note'}, note_lookup, {'error': 'Note not found'}),
            (
                builtin.replace_note_content,
                {'note_id': 'note', 'content': 'forged'},
                note_lookup,
                {'error': 'Note not found', 'code': 'not_found'},
            ),
            (builtin.view_file, {'file_id': 'file'}, file_lookup, {'error': 'File not found'}),
        ):
            saved = lookup.return_value
            assert json.loads(await helper(**args, __user__=user.model_dump(), __request__=object())) == missing
            lookup.return_value = None
            assert json.loads(await helper(**args, __user__=user.model_dump(), __request__=object())) == missing
            lookup.return_value = saved
        for lookup_value in (cal, None):
            calendar_lookup.return_value = lookup_value
            try:
                await calendar._check_calendar_access('calendar', user)
                raise AssertionError('private calendar allowed')
            except HTTPException as exc:
                assert (exc.status_code, exc.detail) == (404, 'Calendar not found')
        calendar_lookup.return_value = cal
        event = SimpleNamespace(id='event', calendar_id='calendar')
        with patch.object(CalendarEvents, 'get_event_by_id', AsyncMock(return_value=event)) as event_lookup:
            for helper in (builtin.update_calendar_event, builtin.delete_calendar_event):
                for lookup_value in (event, None):
                    event_lookup.return_value = lookup_value
                    assert json.loads(
                        await helper(event_id='event', __user__=user.model_dump(), __request__=object())
                    ) == {'error': 'Event not found'}
        # Original upstream admin capabilities must remain when embedding is disabled.
        with patch.object(access, 'settings', replace(access.settings, enabled=False)):
            assert await Chats.get_accessible_chat_by_id('chat', user, chat=chat) is not None
            assert await builtin._has_read_access_to_file(file, user.model_dump()) is True
            assert await calendar._check_calendar_access('calendar', user) == cal
        # Explicit authorization still works; a role alone does not.
        grants.return_value = True
        assert await calendar._check_calendar_access('calendar', user) == cal
    # Listings use owner ID even if upstream BYPASS_ADMIN_ACCESS_CONTROL is true.
    with patch.object(files.Files, 'get_file_list', AsyncMock(return_value=[])) as listing:
        await files.list_files(user=user, page=1, content=True, db=None)
        assert listing.call_args.kwargs['user_id'] == user.id
        with (
            patch.object(access, 'settings', replace(access.settings, enabled=False)),
            patch.object(files, 'BYPASS_ADMIN_ACCESS_CONTROL', True),
        ):
            await files.list_files(user=user, page=1, content=True, db=None)
            assert listing.call_args.kwargs['user_id'] is None
    print('ISOLATION_HOOK_CHECKS_PASS')
