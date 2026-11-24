import { Fragment, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  addComponent,
  archiveBike,
  completeReminder,
  createEvent,
  createSetupLog,
  deleteEvent,
  downloadServiceHistory,
  getBike,
  listComponents,
  listEvents,
  listReminders,
  listSetupLogs,
  snoozeReminder,
  updateEvent,
} from '../api'
import { CHAIN_DEFAULTS } from '../chain'
import { saveBlob } from '../download'
import ChainFields from '../ChainFields'
import type {
  Bike,
  BikeEvent,
  BikeEventUpdate,
  Component,
  EventType,
  Reminder,
  SetupLog,
  SpeedCount,
} from '../types'

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
  // Bumped when completing a reminder adds a service event, so the event
  // list reloads.
  const [eventsVersion, setEventsVersion] = useState(0)

  const [type, setType] = useState('')
  const [installedDate, setInstalledDate] = useState(today)
  const [odometer, setOdometer] = useState('0')
  // Chain-only fields, shown and sent only when the type is exactly "chain".
  const [speedCount, setSpeedCount] = useState<SpeedCount | ''>('')
  const [lifespan, setLifespan] = useState('')
  const isChain = type.trim() === 'chain'

  function chooseSpeedCount(value: SpeedCount) {
    // Prefill the lifespan the API would default to; it stays editable. The
    // wear limit follows from the speed count and isn't sent.
    setSpeedCount(value)
    setLifespan(CHAIN_DEFAULTS[value].lifespanKm)
  }

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
        ...(isChain && {
          speed_count: speedCount === '' ? null : speedCount,
          lifespan_km: lifespan || null,
        }),
      })
      setType('')
      setOdometer('0')
      setSpeedCount('')
      setLifespan('')
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
      <RemindersSection
        bikeId={bikeId}
        components={components}
        onCompleted={() => setEventsVersion((n) => n + 1)}
      />
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

      {/* Shown for archived bikes too: their history is still useful. */}
      <ServiceHistorySection bikeId={bikeId} />

      <SetupLogsSection bikeId={bikeId} archived={archived} />

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
            {isChain && (
              <>
                <ChainFields speedCount={speedCount} onSpeedCount={chooseSpeedCount} />
                <label>
                  Lifespan (km)
                  <input
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={lifespan}
                    onChange={(e) => setLifespan(e.target.value)}
                    required
                  />
                </label>
              </>
            )}
            <button type="submit">Add component</button>
          </form>
        </>
      )}

      <EventsSection
        bikeId={bikeId}
        components={components}
        archived={archived}
        version={eventsVersion}
      />
    </section>
  )
}

function SetupLogsSection({ bikeId, archived }: { bikeId: number; archived: boolean }) {
  const [logs, setLogs] = useState<SetupLog[] | null>(null)
  const [name, setName] = useState('')
  const [reload, setReload] = useState(0)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    listSetupLogs(bikeId)
      .then((data) => {
        if (!ignore) {
          setLogs(data)
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

  async function create(e: FormEvent) {
    e.preventDefault()
    try {
      await createSetupLog(bikeId, name.trim())
      setName('')
      setReload((n) => n + 1)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <>
      <h2>Setup logs</h2>
      {error && <p className="error">{error}</p>}
      {logs !== null &&
        (logs.length === 0 ? (
          <p>No setup logs yet.</p>
        ) : (
          <ul>
            {logs.map((log) => (
              <li key={log.id}>
                <Link to={`/setups/${log.id}`}>{log.name}</Link>
              </li>
            ))}
          </ul>
        ))}
      {!archived && (
        <form onSubmit={create}>
          <label>
            New setup log{' '}
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Race setup"
              required
              maxLength={80}
            />
          </label>{' '}
          <button type="submit">Create</button>
        </form>
      )}
    </>
  )
}

function ServiceHistorySection({ bikeId }: { bikeId: number }) {
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function download(e: FormEvent) {
    e.preventDefault()
    setDownloading(true)
    setError(null)
    try {
      // Blank inputs are left out: no lower or upper bound.
      const { blob, filename } = await downloadServiceHistory(
        bikeId,
        from || undefined,
        to || undefined,
      )
      saveBlob(blob, filename)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <>
      <h2>Service history</h2>
      <form className="stacked" onSubmit={download}>
        <label>
          From (optional)
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label>
          To (optional)
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
        {error && <p className="error">{error}</p>}
        <div>
          <button type="submit" disabled={downloading}>
            {downloading ? 'Downloading…' : 'Download service history'}
          </button>
        </div>
      </form>
    </>
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
  archived,
  version,
}: {
  bikeId: number
  components: Component[]
  archived: boolean
  version: number
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
  }, [bikeId, type, fromDate, toDate, reload, version])

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
      {/* The API rejects new events on archived bikes, so the form is hidden. */}
      {!archived && (
        <AddEventForm
          bikeId={bikeId}
          components={components}
          onAdded={() => setReload((n) => n + 1)}
        />
      )}
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

// Cost and parts, shared by the add and edit event forms. Both are optional:
// blank is sent as null, meaning "not recorded".
function CostAndPartsFields({
  cost,
  parts,
  onCost,
  onParts,
}: {
  cost: string
  parts: string
  onCost: (value: string) => void
  onParts: (value: string) => void
}) {
  return (
    <>
      <label>
        Cost (optional)
        <input
          type="number"
          min="0"
          step="0.01"
          value={cost}
          onChange={(e) => onCost(e.target.value)}
        />
      </label>
      <label>
        Parts (optional)
        <input value={parts} onChange={(e) => onParts(e.target.value)} maxLength={500} />
      </label>
    </>
  )
}

// Cost goes as a string, like odometer_km, so no float rounding on the way.
function costOrNull(cost: string): string | null {
  return cost === '' ? null : cost
}

function partsOrNull(parts: string): string | null {
  return parts.trim() || null
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
  const [cost, setCost] = useState(event.cost ?? '')
  const [parts, setParts] = useState(event.parts ?? '')
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
      cost: costOrNull(cost),
      parts: partsOrNull(parts),
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
      <CostAndPartsFields cost={cost} parts={parts} onCost={setCost} onParts={setParts} />
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

function nowLocalInput(): string {
  return isoToLocalInput(new Date().toISOString())
}

function AddEventForm({
  bikeId,
  components,
  onAdded,
}: {
  bikeId: number
  components: Component[]
  onAdded: () => void
}) {
  const [type, setType] = useState<EventType>('service')
  const [when, setWhen] = useState(nowLocalInput)
  const [componentId, setComponentId] = useState('')
  const [odometer, setOdometer] = useState('')
  const [wear, setWear] = useState('')
  const [note, setNote] = useState('')
  const [cost, setCost] = useState('')
  const [parts, setParts] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const payload: Record<string, unknown> = {}
    if (note.trim()) payload.note = note.trim()
    if (type === 'measurement' && wear !== '') payload.wear_percent = Number(wear)

    setSaving(true)
    setError(null)
    try {
      await createEvent(bikeId, {
        type,
        occurred_at: new Date(when).toISOString(),
        component_id: componentId === '' ? null : Number(componentId),
        odometer_km: odometer === '' ? null : odometer,
        payload: Object.keys(payload).length > 0 ? payload : null,
        cost: costOrNull(cost),
        parts: partsOrNull(parts),
      })
      // Keep the type and component for the next entry; clear the rest.
      setWhen(nowLocalInput())
      setOdometer('')
      setWear('')
      setNote('')
      setCost('')
      setParts('')
      onAdded()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="stacked" onSubmit={submit}>
      <h3>Add event</h3>
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
        Component (optional)
        <select value={componentId} onChange={(e) => setComponentId(e.target.value)}>
          <option value="">None</option>
          {components.map((c) => (
            <option key={c.id} value={c.id}>
              {c.type}
            </option>
          ))}
        </select>
      </label>
      <label>
        Odometer (km, optional)
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
      <CostAndPartsFields cost={cost} parts={parts} onCost={setCost} onParts={setParts} />
      {error && <p className="error">{error}</p>}
      <div>
        <button type="submit" disabled={saving}>
          {saving ? 'Adding…' : 'Add event'}
        </button>
      </div>
    </form>
  )
}

const REMINDER_LABELS: Record<Reminder['kind'], string> = {
  sealant_refill: 'Sealant refill',
}

function RemindersSection({
  bikeId,
  components,
  onCompleted,
}: {
  bikeId: number
  components: Component[]
  onCompleted: () => void
}) {
  const [reminders, setReminders] = useState<Reminder[]>([])
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let ignore = false
    listReminders()
      .then((data) => {
        if (!ignore) {
          // The API returns all of the user's reminders; keep this bike's.
          setReminders(data.filter((r) => r.bike_id === bikeId))
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

  async function complete(reminder: Reminder) {
    try {
      await completeReminder(reminder.id)
      setReload((n) => n + 1)
      onCompleted()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function snooze(reminder: Reminder) {
    const answer = window.prompt('Snooze for how many days? (1–30)', '7')
    if (answer === null) return
    const days = Number(answer.trim())
    if (!Number.isInteger(days)) {
      setError('Enter a whole number of days from 1 to 30.')
      return
    }
    try {
      // The API enforces the 1–30 range and its message is shown on failure.
      await snoozeReminder(reminder.id, days)
      setReload((n) => n + 1)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const componentName = (id: number) =>
    components.find((c) => c.id === id)?.type ?? `component #${id}`

  if (reminders.length === 0 && !error) return null

  return (
    <div className="reminders">
      <h2>Reminders</h2>
      {error && <p className="error">{error}</p>}
      <ul>
        {reminders.map((r) => {
          const overdue = new Date(r.due_at) < new Date()
          return (
            <li key={r.id}>
              {REMINDER_LABELS[r.kind]} ({componentName(r.component_id)}) — due{' '}
              {new Date(r.due_at).toLocaleDateString()}
              {overdue && <strong> (overdue)</strong>}{' '}
              <button type="button" onClick={() => complete(r)}>
                Complete
              </button>{' '}
              <button type="button" onClick={() => snooze(r)}>
                Snooze
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
