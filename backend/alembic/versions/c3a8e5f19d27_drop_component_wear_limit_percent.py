"""drop component wear_limit_percent

The chain wear limit is now derived from speed_count
(app.services.wear.chain_wear_limit), so it's no longer stored.

Revision ID: c3a8e5f19d27
Revises: b7d41c9e2f60
Create Date: 2026-11-24 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a8e5f19d27'
down_revision: Union[str, Sequence[str], None] = 'b7d41c9e2f60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(
        op.f('ck_components_wear_limit_percent_range'), 'components', type_='check'
    )
    op.drop_column('components', 'wear_limit_percent')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'components',
        sa.Column('wear_limit_percent', sa.Numeric(precision=5, scale=2), nullable=True),
    )
    # Refill from speed_count, using the same values as CHAIN_DEFAULTS at the
    # time of this migration, so chains get back the limit they were using.
    # Hard-coded rather than imported: a migration must not change if the app
    # code does.
    op.execute(
        "UPDATE components SET wear_limit_percent = CASE speed_count "
        "WHEN 10 THEN 0.75 WHEN 11 THEN 0.50 END "
        "WHERE type = 'chain' AND speed_count IS NOT NULL"
    )
    op.create_check_constraint(
        op.f('ck_components_wear_limit_percent_range'),
        'components',
        'wear_limit_percent IS NULL OR '
        '(wear_limit_percent > 0 AND wear_limit_percent <= 100)',
    )
