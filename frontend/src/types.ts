// Decimal columns arrive from the API as JSON strings (e.g. "1200.50"),
// so they are typed as string here to avoid losing precision.

export interface BikeDetails {
  frame_type: string | null
  frame_size: string | null
  /** "YYYY-MM-DD" */
  purchase_date: string | null
  purchase_price: string | null
}

export interface Bike extends BikeDetails {
  id: number
  name: string
  created_at: string
  archived_at: string | null
}

// Intervals are stored and returned, but not yet used for health status.
export interface ComponentIntervals {
  refill_interval_days: number | null
  check_interval_km: string | null
}

export interface Component extends ComponentIntervals {
  id: number
  bike_id: number
  type: string
  brand: string | null
  model: string | null
  installed_at: string
  installed_odometer_km: string
  lifespan_km: string | null
  retired_at: string | null
  /** Set only by POST /components/{id}/replace. */
  retired_odometer_km: string | null
  /** Chains only. 10 = "10 or fewer speeds", 11 = "11 or more". The wear
   * limit is derived from it by the API (see Wear.wear_limit_percent). */
  speed_count: SpeedCount | null
}

export type SpeedCount = 10 | 11

export interface ComponentCreate extends Partial<ComponentIntervals> {
  type: string
  installed_at: string
  installed_odometer_km: string
  brand?: string | null
  model?: string | null
  lifespan_km?: string | null
  /** Chains only; the API rejects it on other types. With lifespan_km left
   * out, the API fills it from speed_count. The wear limit can't be sent: the
   * API derives it from speed_count and rejects wear_limit_percent. */
  speed_count?: SpeedCount | null
}

export interface ComponentReplace {
  old_final_odometer_km: string
  new: ComponentCreate
}

export interface ComponentReplaceResult {
  old: Component
  new: Component
}

export interface Mileage {
  component_id: number
  distance_km: string
}

export interface WearPoint {
  occurred_at: string
  odometer_km: string
  wear_percent: string
}

/** Readings (points) are display only. The estimate fields come from ride
 * distance, and are set only for a chain with speed count, lifespan and limit. */
export interface Wear {
  component_id: number
  points: WearPoint[]
  /** limit × (km ridden ÷ lifespan), capped at the limit. */
  estimated_wear_percent: string | null
  /** lifespan − km ridden, floored at 0. */
  estimated_km_remaining: string | null
  /** A chain's limit, derived from its speed count (null without one);
   * "0.75" for other components. */
  wear_limit_percent: string | null
  /** True only for a chain whose estimated wear is at or above cassette_warning_percent. */
  cassette_warning: boolean
  /** Half a chain's limit; null for other components or with no limit. */
  cassette_warning_percent: string | null
  /** Over the bike's rides in the last 90 days; null when there are none. */
  average_km_per_day: string | null
  /** "YYYY-MM-DD" (UTC); null when there isn't enough data. */
  predicted_replacement_date: string | null
}

export type ComponentStatus = 'overdue' | 'due_soon' | 'good' | 'no_lifespan'

export type BikeStatus = ComponentStatus | 'no_components'

export interface ComponentHealth {
  component_id: number
  type: string
  remaining_km: string | null
  status: ComponentStatus
}

export interface BikeHealth {
  id: number
  name: string
  created_at: string
  archived_at: string | null
  status: BikeStatus
  due_count: number
  components: ComponentHealth[]
}

export type EventType = 'service' | 'measurement' | 'part_swap' | 'note'

export interface BikeEvent {
  id: number
  bike_id: number
  component_id: number | null
  type: EventType
  occurred_at: string
  odometer_km: string | null
  payload: Record<string, unknown> | null
  /** Decimal as a string, e.g. "45.50"; null means "not recorded". */
  cost: string | null
  /** Up to 500 characters; null means "not recorded". */
  parts: string | null
  created_at: string
}

/** POST /bikes/{id}/events. occurred_at must include a timezone. */
export interface BikeEventCreate {
  type: EventType
  occurred_at: string
  component_id?: number | null
  odometer_km?: string | null
  payload?: Record<string, unknown> | null
  /** 0 or more, at most 2 decimal places, sent as a string like odometer_km. */
  cost?: string | null
  /** Up to 500 characters. */
  parts?: string | null
}

/** PATCH /events/{id}: omitted fields keep their value; null clears one. */
export interface BikeEventUpdate {
  type?: EventType
  component_id?: number | null
  occurred_at?: string
  odometer_km?: string | null
  payload?: Record<string, unknown> | null
  cost?: string | null
  parts?: string | null
}

export interface EventFilters {
  type?: EventType
  componentId?: number
  /** Timezone-aware ISO timestamps; both bounds are inclusive. */
  from?: string
  to?: string
}

export interface Reminder {
  id: number
  component_id: number
  bike_id: number
  kind: 'sealant_refill'
  status: 'pending' | 'done'
  due_at: string
  completed_at: string | null
  created_at: string
}

/** One torque value. deleted_at is set once a newer value replaced it. */
export interface TorqueValue {
  id: number
  /** Decimal string, e.g. "5.50". */
  torque_nm: string
  created_at: string
  deleted_at: string | null
}

/** GET /components/{id}/torque: one entry per bolt. */
export interface BoltTorque {
  bolt: string
  current: TorqueValue
  /** Every value for the bolt, current included, newest first. */
  history: TorqueValue[]
}

export interface SetupLog {
  id: number
  bike_id: number
  name: string
  created_at: string
}

export interface SetupChange {
  id: number
  setup_log_id: number
  field: string
  old_value: string | null
  new_value: string | null
  changed_at: string
}

export interface SetupChangeCreate {
  field: string
  old_value: string | null
  new_value: string | null
}

/** GET /setups/{id}: the log with one page of changes, oldest first. */
export interface SetupLogDetail extends SetupLog {
  changes: SetupChange[]
  total_changes: number
  limit: number
  offset: number
}
