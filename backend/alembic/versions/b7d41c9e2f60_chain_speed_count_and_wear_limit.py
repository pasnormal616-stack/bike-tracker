"""chain speed count and wear limit

Revision ID: b7d41c9e2f60
Revises: 97f6c5f7c6ba
Create Date: 2026-11-24 22:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d41c9e2f60'
down_revision: Union[str, Sequence[str], None] = '97f6c5f7c6ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Both columns are nullable with no default, so existing rows get NULL and
    # the check constraints below can't fail on them.
    op.add_column('components', sa.Column('speed_count', sa.Integer(), nullable=True))
    op.add_column(
        'components',
        sa.Column('wear_limit_percent', sa.Numeric(precision=5, scale=2), nullable=True),
    )
    op.create_check_constraint(
        op.f('ck_components_speed_count_valid'),
        'components',
        'speed_count IS NULL OR speed_count IN (10, 11)',
    )
    op.create_check_constraint(
        op.f('ck_components_wear_limit_percent_range'),
        'components',
        'wear_limit_percent IS NULL OR '
        '(wear_limit_percent > 0 AND wear_limit_percent <= 100)',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f('ck_components_wear_limit_percent_range'), 'components', type_='check'
    )
    op.drop_constraint(
        op.f('ck_components_speed_count_valid'), 'components', type_='check'
    )
    op.drop_column('components', 'wear_limit_percent')
    op.drop_column('components', 'speed_count')
