"""Версионирование расчётов: цепочка версий, уточнения, экспорты, настройки.

- calculations: parent_id (цепочка версий), status draft|final, version_num,
  finalized_at
- calculation_clarifications: свободнотекстовые уточнения версии + diff
- calculation_exports: файлы 2ПС/КП, привязанные к финализированной версии
- app_settings: настройки (модели экстракции/уточнений — админка админа)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('calculations', sa.Column(
        'parent_id', sa.Integer(), sa.ForeignKey('calculations.id'), nullable=True))
    op.add_column('calculations', sa.Column(
        'status', sa.String(10), nullable=False, server_default='draft'))
    op.add_column('calculations', sa.Column(
        'version_num', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('calculations', sa.Column(
        'finalized_at', sa.DateTime(), nullable=True))

    op.create_table(
        'calculation_clarifications',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('calculation_id', sa.Integer(),
                  sa.ForeignKey('calculations.id'), nullable=False, index=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('diff_json', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.create_table(
        'calculation_exports',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('calculation_id', sa.Integer(),
                  sa.ForeignKey('calculations.id'), nullable=False, index=True),
        sa.Column('kind', sa.String(20), nullable=False),   # 2ps_xlsx|kp_pdf|kp_docx
        sa.Column('file_path', sa.String(1000), nullable=False),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(64), primary_key=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.execute("INSERT INTO app_settings (key, value) VALUES "
               "('extraction_model', 'qwen/qwen3.7-plus'), "
               "('clarification_model', 'qwen/qwen3.7-plus')")


def downgrade() -> None:
    op.drop_table('app_settings')
    op.drop_table('calculation_exports')
    op.drop_table('calculation_clarifications')
    op.drop_column('calculations', 'finalized_at')
    op.drop_column('calculations', 'version_num')
    op.drop_column('calculations', 'status')
    op.drop_column('calculations', 'parent_id')
