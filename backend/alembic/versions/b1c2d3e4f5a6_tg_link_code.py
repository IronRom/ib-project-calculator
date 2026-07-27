"""users.tg_link_code — короткий одноразовый код привязки Telegram

Полный JWT не влезает в Telegram deep-link (start=): ограничение 64 символа и
[A-Za-z0-9_-]. Храним короткий opaque-код с TTL прямо на пользователе.

Revision ID: b1c2d3e4f5a6
Revises: a3b4c5d6e7f8
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tg_link_code", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("tg_link_code_expires", sa.DateTime(), nullable=True))
    op.create_index("ix_users_tg_link_code", "users", ["tg_link_code"])


def downgrade() -> None:
    op.drop_index("ix_users_tg_link_code", table_name="users")
    op.drop_column("users", "tg_link_code_expires")
    op.drop_column("users", "tg_link_code")
