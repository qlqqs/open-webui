"""Require review before adding an admin bypass to personal-resource modules."""

from open_webui.test.embed.audit_admin import scan


def test_no_unreviewed_personal_resource_admin_bypass():
    # These exact remaining conditions are feature/identity/author-trust gates, not
    # resource authority. Knowledge upload is blocked before its legacy branch.
    reviewed = {
        ('routers/files.py', 'upload_file', "user.role != 'admin'"),
        ('routers/files.py', 'get_html_file_content_by_id', "file_user.role != 'admin'"),
        ('routers/files.py', 'process_uploaded_file._process_handler', "user.role == 'admin'"),
        ('routers/notes.py', 'check_notes_access', "user.role != 'admin'"),
        ('routers/calendar.py', 'check_calendar_permission', "user.role != 'admin'"),
        ('routers/calendar.py', '_user_has_automations', "user.role == 'admin'"),
        ('routers/folders.py', 'check_folders_permission', "user.role != 'admin'"),
        ('routers/folders.py', 'delete_folder_by_id', "user.role != 'admin'"),
        ('models/chats.py', 'ChatTable.require_chat_creation_permission', "user.role == 'admin'"),
        ('models/chats.py', 'ChatTable.get_accessible_chat_by_id', "user.role not in {'user', 'admin'}"),
        ('tools/builtin.py', 'create_skill', "__user__.get('role') != 'admin'"),
    }
    files = {item[0] for item in reviewed} | {'utils/files.py', 'utils/access_control/files.py', 'retrieval/utils.py'}
    actual = {
        (item['file'], item['function'], item['expression'])
        for item in scan()
        if item['file'] in files and item['kind'] == 'admin条件'
    }
    assert actual == reviewed
