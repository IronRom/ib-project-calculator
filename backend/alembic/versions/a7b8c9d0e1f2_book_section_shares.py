"""book_section_shares: распределение стоимости по разделам ПД/РД per книга/таблица

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'book_section_shares',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('book_version_id', sa.Integer(), sa.ForeignKey('reference_books.id'), nullable=False, index=True),
        sa.Column('table_num', sa.Integer(), nullable=True, index=True),  # NULL = book-wide
        sa.Column('row_range', sa.String(50), nullable=True),
        sa.Column('stage', sa.String(2), nullable=False),                 # 'ПД' | 'РД'
        sa.Column('section_code', sa.String(20), nullable=False),         # 'ПЗ', 'АР', 'ИОС.ЭС', ...
        sa.Column('section_name', sa.Text(), nullable=False),
        sa.Column('pct', sa.Numeric(6, 3), nullable=False),               # 0-100
    )
    op.create_unique_constraint(
        'uq_section_share', 'book_section_shares',
        ['book_version_id', 'table_num', 'stage', 'section_code'],
    )


def downgrade() -> None:
    op.drop_table('book_section_shares')
