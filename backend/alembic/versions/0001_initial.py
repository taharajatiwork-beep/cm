"""empty message

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Schema is managed via SQLAlchemy Base.metadata.create_all in tests.
    # For Postgres, prefer: alembic revision --autogenerate after Docker is up.
    # This migration creates core tables for greenfield Postgres deploys.
    from app.db.base import Base
    from app import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from app.db.base import Base
    from app import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
