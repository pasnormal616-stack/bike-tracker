import type {
  Bike,
  BikeDetails,
  BikeEvent,
  BikeEventUpdate,
  BikeHealth,
  Component,
  ComponentCreate,
  ComponentReplace,
  ComponentReplaceResult,
  EventFilters,
  Mileage,
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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
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
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
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
