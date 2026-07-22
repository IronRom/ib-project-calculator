"""reference_books: per-book ПД/РД distribution (pd_pct, rd_pct)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reference_books', sa.Column('pd_pct', sa.Numeric(4, 3), nullable=True))
    op.add_column('reference_books', sa.Column('rd_pct', sa.Numeric(4, 3), nullable=True))


def downgrade() -> None:
    op.drop_column('reference_books', 'rd_pct')
    op.drop_column('reference_books', 'pd_pct')
