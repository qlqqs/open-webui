"""One-shot workbench initialization; the user's settings are the authority.

A conditional UPDATE makes concurrent first visits harmless and never overwrites
an explicit Key selection/clear. No second database is required for this marker.
"""
from sqlalchemy import update, or_
from open_webui.models.users import User, UserModel


async def initialize_settings(user_id, patch, db):
    user = await db.get(User, user_id)
    if user is None:
        return None
    current = dict(user.settings or {})
    ui = dict(current.get('ui') or {})
    if 'sub2api' in ui or ui.get('sub2api_initialized') or ui.get('models'):
        return UserModel.model_validate(user)
    ui.update(patch.get('ui') or {})
    ui['sub2api_initialized'] = True
    current['ui'] = ui
    # JSON path extraction works for both SQLite and PostgreSQL. Missing values
    # yield SQL NULL; a deliberately cleared selection is an object, not NULL.
    await db.execute(
        update(User).where(
            User.id == user_id,
            User.settings['ui']['sub2api'].as_string().is_(None),
            User.settings['ui']['sub2api_initialized'].as_boolean().is_not(True),
            or_(User.settings['ui']['models'].as_string().is_(None), User.settings['ui']['models'].as_string() == '[]'),
        ).values(settings=current).execution_options(synchronize_session=False)
    )
    await db.commit()
    await db.refresh(user)
    return UserModel.model_validate(user)
