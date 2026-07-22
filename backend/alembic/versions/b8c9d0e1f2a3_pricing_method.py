"""reference_books.pricing_method: методика ценообразования книги

'mu620'  — МУ №620 (СБЦП): экстраполяция в пределах [Xмин/2; 2×Xмакс],
           вне пределов п.2.1.3/2.1.4 требуют калькуляции 3П (движок
           консервативно ограничивает X и предупреждает)
'707pr'  — Методика 707/пр (НЗ): вверх ф.8.3 без ограничения,
           вниз ф.8.4/8.5 (Кэ ≥ 0,1)
'mrr'    — МРР (Москва): вверх ф.2.2 сборников (a + в·Xмакс + в·ΔX·0,5)

Бэкфилл по price_base_year: 2000 → mrr, ≥2020 → 707pr, иначе mu620.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reference_books', sa.Column(
        'pricing_method', sa.String(10), nullable=False, server_default='mu620'))
    op.execute("UPDATE reference_books SET pricing_method='mrr' WHERE price_base_year=2000")
    op.execute("UPDATE reference_books SET pricing_method='707pr' WHERE price_base_year>=2020")


def downgrade() -> None:
    op.drop_column('reference_books', 'pricing_method')
