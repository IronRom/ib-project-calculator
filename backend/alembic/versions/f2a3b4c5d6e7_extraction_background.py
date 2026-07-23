"""calculations: статус фоновой AI-экстракции ТЗ.

Анализ ТЗ запускается фоновой задачей на сервере; прогресс и ошибки
хранятся в БД, чтобы клиент мог закрыть вкладку и вернуться позже.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('calculations', sa.Column(
        'extraction_status', sa.String(10), nullable=False,
        server_default='idle'))  # idle | running | done | error
    op.add_column('calculations', sa.Column(
        'extraction_progress', JSONB(), nullable=True))  # {step,total,message}
    op.add_column('calculations', sa.Column(
        'extraction_error', sa.Text(), nullable=True))
    op.add_column('calculations', sa.Column(
        'extraction_started_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('calculations', 'extraction_started_at')
    op.drop_column('calculations', 'extraction_error')
    op.drop_column('calculations', 'extraction_progress')
    op.drop_column('calculations', 'extraction_status')
