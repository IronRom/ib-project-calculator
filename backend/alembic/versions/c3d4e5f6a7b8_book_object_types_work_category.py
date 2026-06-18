"""add work_category to book_object_types

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# НЗ-2025-МС281-ИГИ table → work_category mapping (Table 1 НЗ 281/пр)
_WC: dict[int, str] = {
    12: 'field', 14: 'field', 16: 'field', 18: 'field',
    20: 'field', 22: 'field', 24: 'field',
    28: 'field', 29: 'field', 30: 'field', 31: 'field', 32: 'field',
    33: 'kameral',
    34: 'field', 35: 'field', 36: 'kameral',
    37: 'field', 38: 'kameral', 39: 'field', 40: 'kameral',
    41: 'field', 42: 'kameral',
    43: 'field', 44: 'field', 45: 'kameral',
    47: 'field', 48: 'kameral',
    50: 'field', 51: 'kameral',
    52: 'field', 53: 'kameral',
    54: 'field', 55: 'kameral',
    56: 'lab', 57: 'lab', 58: 'lab', 59: 'lab', 60: 'lab', 61: 'lab',
    62: 'kameral',
    63: 'lab', 64: 'kameral',
    65: 'kameral',
    66: 'program',
}


def upgrade() -> None:
    op.add_column(
        'book_object_types',
        sa.Column('work_category', sa.String(20), nullable=True, server_default='field'),
    )

    # Populate existing rows from table_num → category mapping.
    # server_default fills all rows with 'field'; override non-field categories.
    conn = op.get_bind()
    non_field = {k: v for k, v in _WC.items() if v != 'field'}
    for table_num, category in non_field.items():
        conn.execute(
            sa.text(
                "UPDATE book_object_types SET work_category = :cat "
                "WHERE table_num = :tnum"
            ),
            {"cat": category, "tnum": table_num},
        )


def downgrade() -> None:
    op.drop_column('book_object_types', 'work_category')
