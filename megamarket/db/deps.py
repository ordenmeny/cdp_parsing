from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from megamarket.db.helper import async_session_manager, sync_session_manager

SyncSessionDep = Annotated[
    Session,
    Depends(sync_session_manager.get_session),
]
AsyncSessionDep = Annotated[
    AsyncSession,
    Depends(async_session_manager.get_session),
]
