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
}

export interface ComponentCreate extends Partial<ComponentIntervals> {
  type: string
  installed_at: string
  installed_odometer_km: string
  brand?: string | null
  model?: string | null
  lifespan_km?: string | null
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

export interface Wear {
  component_id: number
  points: WearPoint[]
  estimated_km_remaining: string | null
  wear_limit_percent: string
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
  created_at: string
}
