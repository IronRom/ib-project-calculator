"""add asutp_factor_options, asutp_modules, calc_method to reference_books

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'reference_books',
        sa.Column('calc_method', sa.String(length=20), nullable=False, server_default='standard'),
    )

    op.create_table(
        'asutp_factor_options',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('book_version_id', sa.Integer(), nullable=False),
        sa.Column('factor_code', sa.String(length=5), nullable=False),
        sa.Column('factor_name', sa.Text(), nullable=False),
        sa.Column('option_code', sa.String(length=20), nullable=False),
        sa.Column('option_description', sa.Text(), nullable=False),
        sa.Column('score_or', sa.SmallInteger(), nullable=True),
        sa.Column('score_oo', sa.SmallInteger(), nullable=True),
        sa.Column('score_io', sa.SmallInteger(), nullable=True),
        sa.Column('score_to', sa.SmallInteger(), nullable=True),
        sa.Column('score_mo', sa.SmallInteger(), nullable=True),
        sa.Column('score_po', sa.SmallInteger(), nullable=True),
        sa.ForeignKeyConstraint(['book_version_id'], ['reference_books.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_asutp_factor_options_id', 'asutp_factor_options', ['id'])
    op.create_index('ix_asutp_factor_options_book', 'asutp_factor_options', ['book_version_id'])
    op.create_index('ix_asutp_factor_options_factor', 'asutp_factor_options',
                    ['book_version_id', 'factor_code', 'option_code'])

    op.create_table(
        'asutp_modules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('book_version_id', sa.Integer(), nullable=False),
        sa.Column('module_code', sa.String(length=5), nullable=False),
        sa.Column('s_value', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('stage_r_min', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('stage_r_max', sa.SmallInteger(), nullable=False, server_default='100'),
        sa.Column('stage_p_min', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('stage_p_max', sa.SmallInteger(), nullable=False, server_default='100'),
        sa.ForeignKeyConstraint(['book_version_id'], ['reference_books.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_asutp_modules_id', 'asutp_modules', ['id'])
    op.create_index('ix_asutp_modules_book', 'asutp_modules', ['book_version_id'])


def downgrade() -> None:
    op.drop_index('ix_asutp_modules_book', table_name='asutp_modules')
    op.drop_index('ix_asutp_modules_id', table_name='asutp_modules')
    op.drop_table('asutp_modules')
    op.drop_index('ix_asutp_factor_options_factor', table_name='asutp_factor_options')
    op.drop_index('ix_asutp_factor_options_book', table_name='asutp_factor_options')
    op.drop_index('ix_asutp_factor_options_id', table_name='asutp_factor_options')
    op.drop_table('asutp_factor_options')
    op.drop_column('reference_books', 'calc_method')
