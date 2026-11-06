"""Initial PAP core database schema (all 19 ERD tables + telemetry/command/event tables).

Revision ID: 0001_initial_pap_core
Revises:
Create Date: 2026-11-02 08:00:00
"""

from typing import Sequence, Union

from alembic import op

from app.core.database import Base
from app.modules import import_all_models

revision: str = "0001_initial_pap_core"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    import_all_models()
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    import_all_models()
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)

