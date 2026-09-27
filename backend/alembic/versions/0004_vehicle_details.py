"""Add rich vehicle detail columns."""

from alembic import op
import sqlalchemy as sa


revision = "0004_vehicle_details"
down_revision = "0003_campaigns"
branch_labels = None
depends_on = None

_COLS = [
    ("description", sa.Text()),
    ("notes", sa.Text()),
    ("body_type", sa.String(50)),
    ("transmission", sa.String(50)),
    ("fuel_type", sa.String(50)),
    ("engine", sa.String(80)),
    ("plate_number", sa.String(40)),
    ("doors", sa.Integer()),
    ("seats", sa.Integer()),
    ("options", sa.Text()),
    ("exterior_condition", sa.String(80)),
    ("interior_condition", sa.String(80)),
    ("import_source", sa.String(120)),
]


def upgrade() -> None:
    for name, col_type in _COLS:
        op.add_column("vehicles", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(_COLS):
        op.drop_column("vehicles", name)
