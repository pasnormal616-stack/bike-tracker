import type {
  Bike,
  BikeDetails,
  BikeEvent,
  BikeEventCreate,
  BikeEventUpdate,
  BikeHealth,
  Component,
  ComponentCreate,
  ComponentReplace,
  ComponentReplaceResult,
  EventFilters,
  Mileage,
  Reminder,
  SetupChange,
  SetupChangeCreate,
  SetupLog,
  SetupLogDetail,
  BoltTorque,
  Wear,
} from './types'

const BASE_URL: string =
  import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

export const USER_ID_KEY = 'userId'

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(`${status}: ${detail}`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

// FastAPI sends {"detail": "..."} for HTTPException and
// {"detail": [{"msg": "..."}, ...]} for validation errors.
async function readDetail(response: Response): Promise<string> {
  try {
    const body = await response.json()
    const detail = body?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail.map((item) => item?.msg ?? JSON.stringify(item)).join('; ')
    }
  } catch {
    // Body wasn't JSON; fall through to the status text.
  }
  return response.statusText || 'Request failed'
}

// Sends a request with the x-user-id header and throws ApiError unless the
// response is OK. Shared by JSON requests and file downloads.
async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const userId = localStorage.getItem(USER_ID_KEY)
  if (!userId) {
    throw new Error('No user id set. Enter one in the top bar.')
  }

  const headers = new Headers(init.headers)
  headers.set('x-user-id', userId)
  if (init.body !== undefined) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers })
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response))
  }
  return response
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await send(path, init)
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

// The file name from a Content-Disposition header. Prefers the RFC 5987
// filename*=UTF-8''... form, then filename="...". Null if neither is there.
export function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null
  const encoded = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(header)
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim())
    } catch {
      // Malformed encoding; fall back to the plain form.
    }
  }
  const plain = /filename\s*=\s*"([^"]*)"|filename\s*=\s*([^;]+)/i.exec(header)
  const name = (plain?.[1] ?? plain?.[2])?.trim()
  return name || null
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

export function listBikes(): Promise<Bike[]> {
  return request('/bikes')
}

export function listBikeHealth(): Promise<BikeHealth[]> {
  return request('/bikes/summary')
}

export function createBike(
  name: string,
  details: Partial<BikeDetails> = {},
): Promise<Bike> {
  return post('/bikes', { name, ...details })
}

export function getBike(bikeId: number): Promise<Bike> {
  return request(`/bikes/${bikeId}`)
}

export function archiveBike(bikeId: number): Promise<Bike> {
  return post(`/bikes/${bikeId}/archive`)
}

export function listComponents(bikeId: number): Promise<Component[]> {
  return request(`/bikes/${bikeId}/components`)
}

export function addComponent(
  bikeId: number,
  component: ComponentCreate,
): Promise<Component> {
  return post(`/bikes/${bikeId}/components`, component)
}

export function getComponent(componentId: number): Promise<Component> {
  return request(`/components/${componentId}`)
}

export function getMileage(componentId: number): Promise<Mileage> {
  return request(`/components/${componentId}/mileage`)
}

export function getWear(componentId: number): Promise<Wear> {
  return request(`/components/${componentId}/wear`)
}

export function retireComponent(componentId: number): Promise<Component> {
  return post(`/components/${componentId}/retire`)
}

export function replaceComponent(
  componentId: number,
  replacement: ComponentReplace,
): Promise<ComponentReplaceResult> {
  return post(`/components/${componentId}/replace`, replacement)
}

export function listEvents(
  bikeId: number,
  filters: EventFilters = {},
): Promise<BikeEvent[]> {
  const params = new URLSearchParams()
  if (filters.type) params.set('type', filters.type)
  if (filters.componentId !== undefined) {
    params.set('component_id', String(filters.componentId))
  }
  if (filters.from) params.set('from', filters.from)
  if (filters.to) params.set('to', filters.to)
  const query = params.toString()
  return request(`/bikes/${bikeId}/events${query ? `?${query}` : ''}`)
}

export function updateEvent(
  eventId: number,
  changes: BikeEventUpdate,
): Promise<BikeEvent> {
  return request(`/events/${eventId}`, {
    method: 'PATCH',
    body: JSON.stringify(changes),
  })
}

export function deleteEvent(eventId: number): Promise<void> {
  return request(`/events/${eventId}`, { method: 'DELETE' })
}

export function createEvent(
  bikeId: number,
  event: BikeEventCreate,
): Promise<BikeEvent> {
  return post(`/bikes/${bikeId}/events`, event)
}

export interface FileDownload {
  blob: Blob
  filename: string
}

/** GET /bikes/{id}/service-history.pdf. from and to are optional
 * "YYYY-MM-DD" dates, both inclusive. Fetched (not a plain link) so the
 * x-user-id header is sent. */
export async function downloadServiceHistory(
  bikeId: number,
  from?: string,
  to?: string,
): Promise<FileDownload> {
  const params = new URLSearchParams()
  if (from) params.set('from', from)
  if (to) params.set('to', to)
  const query = params.toString()
  const response = await send(
    `/bikes/${bikeId}/service-history.pdf${query ? `?${query}` : ''}`,
  )
  return {
    blob: await response.blob(),
    filename:
      filenameFromDisposition(response.headers.get('Content-Disposition')) ??
      `service-history-${bikeId}.pdf`,
  }
}

/** The user's pending reminders across all bikes, soonest first. */
export function listReminders(): Promise<Reminder[]> {
  return request('/reminders')
}

export function completeReminder(reminderId: number): Promise<Reminder> {
  return post(`/reminders/${reminderId}/complete`)
}

export function snoozeReminder(reminderId: number, days: number): Promise<Reminder> {
  return post(`/reminders/${reminderId}/snooze`, { days })
}

export function listTorque(componentId: number): Promise<BoltTorque[]> {
  return request(`/components/${componentId}/torque`)
}

/** Sets a bolt's torque. The old value is kept in the bolt's history. */
export function setTorque(
  componentId: number,
  bolt: string,
  torqueNm: string,
): Promise<BoltTorque> {
  return post(`/components/${componentId}/torque`, { bolt, torque_nm: torqueNm })
}

export function listSetupLogs(bikeId: number): Promise<SetupLog[]> {
  return request(`/bikes/${bikeId}/setups`)
}

export function createSetupLog(bikeId: number, name: string): Promise<SetupLog> {
  return post(`/bikes/${bikeId}/setups`, { name })
}

export function getSetupLog(
  setupId: number,
  limit = 50,
  offset = 0,
): Promise<SetupLogDetail> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  return request(`/setups/${setupId}?${params}`)
}

export function addSetupChange(
  setupId: number,
  change: SetupChangeCreate,
): Promise<SetupChange> {
  return post(`/setups/${setupId}/changes`, change)
}

export function deleteSetupLog(setupId: number): Promise<void> {
  return request(`/setups/${setupId}`, { method: 'DELETE' })
}

/** GET /me/export: every row the user owns, as a JSON file. */
export async function exportMyData(): Promise<FileDownload> {
  const response = await send('/me/export')
  return {
    blob: await response.blob(),
    filename:
      filenameFromDisposition(response.headers.get('Content-Disposition')) ??
      'bike-tracker-export.json',
  }
}

export const DELETE_CONFIRMATION = 'DELETE MY DATA'

/** POST /me/delete: permanently deletes the user and all their data. */
export function deleteMyAccount(): Promise<void> {
  return post('/me/delete', { confirm: DELETE_CONFIRMATION })
}
