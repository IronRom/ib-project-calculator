"""widen reference_rows varchar columns

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('reference_rows', 'x_unit',
                    type_=sa.String(100), existing_nullable=True)
    op.alter_column('reference_rows', 'row_num',
                    type_=sa.String(20), existing_nullable=True)


def downgrade() -> None:
    op.alter_column('reference_rows', 'x_unit',
                    type_=sa.String(30), existing_nullable=True)
    op.alter_column('reference_rows', 'row_num',
                    type_=sa.String(10), existing_nullable=True)
