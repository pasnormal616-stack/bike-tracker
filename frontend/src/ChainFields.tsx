import { CHAIN_DEFAULTS, SPEED_COUNT_LABELS } from './chain'
import type { SpeedCount } from './types'

/** The speed count select shown on chain forms, with the wear limit it
 * implies as read-only text. Picking a speed count calls onSpeedCount, so the
 * form can prefill the lifespan from CHAIN_DEFAULTS. */
export default function ChainFields({
  speedCount,
  onSpeedCount,
}: {
  speedCount: SpeedCount | ''
  onSpeedCount: (value: SpeedCount) => void
}) {
  return (
    <>
      <label>
        Speed count
        <select
          value={speedCount}
          onChange={(e) => onSpeedCount(Number(e.target.value) as SpeedCount)}
          required
        >
          <option value="" disabled>
            Choose…
          </option>
          {([10, 11] as const).map((value) => (
            <option key={value} value={value}>
              {SPEED_COUNT_LABELS[value]}
            </option>
          ))}
        </select>
      </label>
      {speedCount !== '' && (
        <p className="derived">
          Wear limit: {CHAIN_DEFAULTS[speedCount].wearLimitPercent}% (
          {SPEED_COUNT_LABELS[speedCount]})
        </p>
      )}
    </>
  )
}
