"""users.telegram_id / telegram_username: привязка Telegram-бота

telegram_id — BigInteger (id пользователя/чата Telegram выходят за int32),
unique NULL = не привязан. Привязка выполняется через бота по одноразовому
подписанному коду из личного кабинета (POST /auth/telegram/link).

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-07-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('telegram_id', sa.BigInteger(), nullable=True))
    op.add_column('users', sa.Column('telegram_username', sa.String(64), nullable=True))
    op.create_unique_constraint('uq_users_telegram_id', 'users', ['telegram_id'])
    op.create_index('ix_users_telegram_id', 'users', ['telegram_id'])


def downgrade() -> None:
    op.drop_index('ix_users_telegram_id', table_name='users')
    op.drop_constraint('uq_users_telegram_id', 'users', type_='unique')
    op.drop_column('users', 'telegram_username')
    op.drop_column('users', 'telegram_id')
