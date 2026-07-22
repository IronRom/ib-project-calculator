"""reference_books.region: региональная привязка справочника

NULL = федеральный. Заполнено 'Москва и МО' для МРР-книг (bэкфилл по
price_base_year=2000 — все текущие МРР; для новых книг задаётся при импорте).

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reference_books', sa.Column('region', sa.String(50), nullable=True))
    op.execute("UPDATE reference_books SET region='Москва и МО' WHERE pricing_method='mrr'")


def downgrade() -> None:
    op.drop_column('reference_books', 'region')
