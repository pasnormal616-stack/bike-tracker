import type { SpeedCount } from './types'

export const SPEED_COUNT_LABELS: Record<SpeedCount, string> = {
  10: '10 or fewer',
  11: '11 or more',
}

// Mirrors CHAIN_DEFAULTS in backend/app/services/wear.py. The limit is fixed
// by the speed count and only shown here; the API derives it and rejects any
// attempt to set it. The lifespan is a default that stays editable.
export const CHAIN_DEFAULTS: Record<SpeedCount, { wearLimitPercent: string; lifespanKm: string }> = {
  10: { wearLimitPercent: '0.75', lifespanKm: '3000' },
  11: { wearLimitPercent: '0.50', lifespanKm: '2500' },
}
