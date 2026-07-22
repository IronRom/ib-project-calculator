"""book_conditions: apply_mode (multiply | additive) — universal coefficient combining

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('book_conditions', sa.Column('apply_mode', sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column('book_conditions', 'apply_mode')
