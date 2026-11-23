import { Fragment, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  addComponent,
  archiveBike,
  deleteEvent,
  getBike,
  listComponents,
  listEvents,
  updateEvent,
} from '../api'
import type { Bike, BikeEvent, BikeEventUpdate, Component, EventType } from '../types'

// A date input gives "YYYY-MM-DD"; store it as local midnight in ISO form,
// so rides later that day count toward the component's mileage.
function dateToIso(date: string): string {
  return new Date(`${date}T00:00:00`).toISOString()
}

// "YYYY-MM-DD" parsed as a local date; new Date("YYYY-MM-DD") would be UTC
// and can show the previous day west of Greenwich.
function formatPlainDate(value: string): string {
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString()
}

function today(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

export default function BikePage() {
  const bikeId = Number(useParams().bikeId)
  const navigate = useNavigate()

  const [bike, setBike] = useState<Bike | null>(null)
  const [components, setComponents] = useState<Component[]>([])
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)

  const [type, setType] = useState('')
  const [installedDate, setInstalledDate] = useState(today)
  const [odometer, setOdometer] = useState('0')

  useEffect(() => {
    let ignore = false
    Promise.all([getBike(bikeId), listComponents(bikeId)])
      .then(([bikeData, componentData]) => {
        if (!ignore) {
          setBike(bikeData)
          setComponents(componentData)
          setError(null)
        }
      })
      .catch((e: Error) => {
        if (!ignore) setError(e.message)
      })
    return () => {
      ignore = true
    }
  }, [bikeId, reload])

  async function archive() {
    if (!bike || !window.confirm(`Archive ${bike.name}?`)) return
    try {
      await archiveBike(bikeId)
      navigate('/')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function add(event: FormEvent) {
    event.preventDefault()
    try {
      await addComponent(bikeId, {
        type: type.trim(),
        installed_at: dateToIso(installedDate),
        installed_odometer_km: odometer,
      })
      setType('')
      setOdometer('0')
      setReload((n) => n + 1)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (!bike) {
    return error ? <p className="error">{error}</p> : <p>Loading…</p>
  }

  const archived = bike.archived_at !== null
  const details: [string, string][] = []
  if (bike.frame_type) details.push(['Type', bike.frame_type])
  if (bike.frame_size) details.push(['Frame size', bike.frame_size])
  if (bike.purchase_date) {
    details.push(['Purchased', formatPlainDate(bike.purchase_date)])
  }
  if (bike.purchase_price !== null) details.push(['Price', bike.purchase_price])

  return (
    <section>
      <p>
        <Link to="/">← All bikes</Link>
      </p>
      <h1>
        {bike.name}
        {archived && <span className="badge">archived</span>}
      </h1>
      {details.length > 0 && (
        <dl className="details">
          {details.map(([label, value]) => (
            <Fragment key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </Fragment>
          ))}
        </dl>
      )}
      {error && <p className="error">{error}</p>}
      {!archived && (
        <button type="button" onClick={archive}>
          Archive bike
        </button>
      )}

      <h2>Components</h2>
      {components.length === 0 ? (
        <p>No active components.</p>
      ) : (
        <ul>
          {components.map((c) => (
            <li key={c.id}>
              <Link to={`/components/${c.id}`}>
                {c.type}
                {c.brand || c.model
                  ? ` (${[c.brand, c.model].filter(Boolean).join(' ')})`
                  : ''}
              </Link>
            </li>
          ))}
        </ul>
      )}

      {!archived && (
        <>
          <h2>Add a component</h2>
          <form className="stacked" onSubmit={add}>
            <label>
              Type
              <input
                value={type}
                onChange={(e) => setType(e.target.value)}
                placeholder="chain"
                required
                maxLength={50}
              />
            </label>
            <label>
              Installed on
              <input
                type="date"
                value={installedDate}
                onChange={(e) => setInstalledDate(e.target.value)}
                required
              />
            </label>
            <label>
              Installed odometer (km)
              <input
                type="number"
                min="0"
                step="0.01"
                value={odometer}
                onChange={(e) => setOdometer(e.target.value)}
                required
              />
            </label>
            <button type="submit">Add component</button>
          </form>
        </>
      )}

      <EventsSection bikeId={bikeId} components={components} />
    </section>
  )
}

const EVENT_TYPES: EventType[] = ['service', 'measurement', 'part_swap', 'note']

const EVENT_TYPE_LABELS: Record<EventType, string> = {
  service: 'Service',
  measurement: 'Measurement',
  part_swap: 'Part swap',
  note: 'Note',
}

// <input type="datetime-local"> works in local "YYYY-MM-DDTHH:mm".
function isoToLocalInput(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  )
}

function describePayload(payload: BikeEvent['payload']): string {
  if (!payload) return ''
  const parts: string[] = []
  if (payload.wear_percent !== undefined) parts.push(`wear ${String(payload.wear_percent)}%`)
  if (typeof payload.note === 'string' && payload.note) parts.push(payload.note)
  return parts.join(' · ')
}

function EventsSection({
  bikeId,
  components,
}: {
  bikeId: number
  components: Component[]
}) {
  const [events, setEvents] = useState<BikeEvent[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [type, setType] = useState<EventType | ''>('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let ignore = false
    listEvents(bikeId, {
      type: type || undefined,
      // Whole days in local time; the API treats both bounds as inclusive.
      from: fromDate ? new Date(`${fromDate}T00:00:00`).toISOString() : undefined,
      to: toDate ? new Date(`${toDate}T23:59:59.999`).toISOString() : undefined,
    })
      .then((data) => {
        if (!ignore) {
          setEvents(data)
          setError(null)
        }
      })
      .catch((e: Error) => {
        if (!ignore) setError(e.message)
      })
    return () => {
      ignore = true
    }
  }, [bikeId, type, fromDate, toDate, reload])

  async function remove(event: BikeEvent) {
    const label = EVENT_TYPE_LABELS[event.type].toLowerCase()
    if (!window.confirm(`Delete this ${label} event?`)) return
    try {
      await deleteEvent(event.id)
      setReload((n) => n + 1)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const componentName = (id: number | null) => {
    if (id === null) return ''
    const component = components.find((c) => c.id === id)
    return component ? component.type : `component #${id}`
  }

  return (
    <>
      <h2>Events</h2>
      <div className="filters">
        <label>
          Type{' '}
          <select value={type} onChange={(e) => setType(e.target.value as EventType | '')}>
            <option value="">All</option>
            {EVENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {EVENT_TYPE_LABELS[t]}
              </option>
            ))}
          </select>
        </label>{' '}
        <label>
          From <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
        </label>{' '}
        <label>
          To <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
        </label>
      </div>
      {error && <p className="error">{error}</p>}
      {events === null && !error && <p>Loading…</p>}
      {events !== null &&
        (events.length === 0 ? (
          <p>No events.</p>
        ) : (
          <ul className="events">
            {events.map((event) =>
              editingId === event.id ? (
                <li key={event.id}>
                  <EventEditForm
                    event={event}
                    components={components}
                    onCancel={() => setEditingId(null)}
                    onSaved={() => {
                      setEditingId(null)
                      setReload((n) => n + 1)
                    }}
                  />
                </li>
              ) : (
                <li key={event.id}>
                  {new Date(event.occurred_at).toLocaleString()} —{' '}
                  {EVENT_TYPE_LABELS[event.type]}
                  {event.component_id !== null && ` (${componentName(event.component_id)})`}
                  {event.odometer_km !== null && ` at ${event.odometer_km} km`}
                  {describePayload(event.payload) && ` — ${describePayload(event.payload)}`}{' '}
                  <button type="button" onClick={() => setEditingId(event.id)}>
                    Edit
                  </button>{' '}
                  <button type="button" onClick={() => remove(event)}>
                    Delete
                  </button>
                </li>
              ),
            )}
          </ul>
        ))}
    </>
  )
}

function EventEditForm({
  event,
  components,
  onCancel,
  onSaved,
}: {
  event: BikeEvent
  components: Component[]
  onCancel: () => void
  onSaved: () => void
}) {
  const initialWhen = isoToLocalInput(event.occurred_at)
  const [type, setType] = useState<EventType>(event.type)
  const [when, setWhen] = useState(initialWhen)
  const [odometer, setOdometer] = useState(event.odometer_km ?? '')
  const [componentId, setComponentId] = useState(
    event.component_id === null ? '' : String(event.component_id),
  )
  const [note, setNote] = useState(
    typeof event.payload?.note === 'string' ? event.payload.note : '',
  )
  const [wear, setWear] = useState(
    event.payload?.wear_percent === undefined ? '' : String(event.payload.wear_percent),
  )
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // The current component stays selectable even if it's retired (active
  // components are all the bike page loads).
  const options = components.map((c) => ({ id: c.id, label: c.type }))
  if (event.component_id !== null && !options.some((o) => o.id === event.component_id)) {
    options.push({ id: event.component_id, label: `component #${event.component_id}` })
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    // Keep any other payload keys; only note and wear_percent are edited here.
    const payload: Record<string, unknown> = { ...(event.payload ?? {}) }
    if (note.trim()) payload.note = note.trim()
    else delete payload.note
    if (type === 'measurement') {
      if (wear === '') delete payload.wear_percent
      else payload.wear_percent = Number(wear)
    }
    const changes: BikeEventUpdate = {
      type,
      component_id: componentId === '' ? null : Number(componentId),
      odometer_km: odometer === '' ? null : odometer,
      payload: Object.keys(payload).length > 0 ? payload : null,
    }
    // A datetime-local input has minute precision, so only send the time
    // when it was changed; otherwise the seconds would be lost.
    if (when !== initialWhen) changes.occurred_at = new Date(when).toISOString()

    setSaving(true)
    setError(null)
    try {
      await updateEvent(event.id, changes)
      onSaved()
    } catch (err) {
      setError((err as Error).message)
      setSaving(false)
    }
  }

  return (
    <form className="stacked" onSubmit={submit}>
      <label>
        Type
        <select value={type} onChange={(e) => setType(e.target.value as EventType)}>
          {EVENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {EVENT_TYPE_LABELS[t]}
            </option>
          ))}
        </select>
      </label>
      <label>
        When
        <input
          type="datetime-local"
          value={when}
          onChange={(e) => setWhen(e.target.value)}
          required
        />
      </label>
      <label>
        Component
        <select value={componentId} onChange={(e) => setComponentId(e.target.value)}>
          <option value="">None</option>
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Odometer (km)
        <input
          type="number"
          min="0"
          step="0.01"
          value={odometer}
          onChange={(e) => setOdometer(e.target.value)}
        />
      </label>
      {type === 'measurement' && (
        <label>
          Wear (%)
          <input
            type="number"
            min="0"
            max="100"
            step="any"
            value={wear}
            onChange={(e) => setWear(e.target.value)}
          />
        </label>
      )}
      <label>
        Note
        <input value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      {error && <p className="error">{error}</p>}
      <div>
        <button type="submit" disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </button>{' '}
        <button type="button" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </form>
  )
}
