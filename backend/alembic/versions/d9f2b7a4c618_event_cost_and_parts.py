"""event cost and parts

Revision ID: d9f2b7a4c618
Revises: c3a8e5f19d27
Create Date: 2026-11-24 23:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9f2b7a4c618'
down_revision: Union[str, Sequence[str], None] = 'c3a8e5f19d27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Both nullable with no default: existing events get NULL ("not
    # recorded"), so the check constraints can't fail on them.
    op.add_column('events', sa.Column('cost', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('events', sa.Column('parts', sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f('ck_events_cost_non_negative'),
        'events',
        'cost IS NULL OR cost >= 0',
    )
    op.create_check_constraint(
        op.f('ck_events_parts_max_length'),
        'events',
        'parts IS NULL OR char_length(parts) <= 500',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_events_parts_max_length'), 'events', type_='check')
    op.drop_constraint(op.f('ck_events_cost_non_negative'), 'events', type_='check')
    op.drop_column('events', 'parts')
    op.drop_column('events', 'cost')
