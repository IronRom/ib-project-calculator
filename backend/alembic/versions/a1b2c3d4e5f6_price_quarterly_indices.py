"""add price_quarterly_indices and price_base_year

Revision ID: a1b2c3d4e5f6
Revises: 5506a0c35379
Create Date: 2026-06-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '5506a0c35379'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'price_quarterly_indices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('quarter', sa.Integer(), nullable=False),
        sa.Column('base_year', sa.Integer(), nullable=False),
        sa.Column('work_type', sa.String(length=20), nullable=False, server_default='project'),
        sa.Column('index_value', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('source_ref', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('year', 'quarter', 'base_year', 'work_type', name='uq_quarterly_index'),
    )
    op.create_index('ix_price_quarterly_indices_id', 'price_quarterly_indices', ['id'])

    op.add_column(
        'reference_books',
        sa.Column('price_base_year', sa.Integer(), nullable=False, server_default='2001'),
    )


def downgrade() -> None:
    op.drop_column('reference_books', 'price_base_year')
    op.drop_index('ix_price_quarterly_indices_id', table_name='price_quarterly_indices')
    op.drop_table('price_quarterly_indices')
