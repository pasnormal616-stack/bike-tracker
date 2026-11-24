import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  createEvent,
  getBike,
  getComponent,
  getMileage,
  getWear,
  replaceComponent,
  retireComponent,
} from '../api'
import { CHAIN_DEFAULTS, SPEED_COUNT_LABELS } from '../chain'
import ChainFields from '../ChainFields'
import type {
  Bike,
  Component,
  ComponentReplaceResult,
  Mileage,
  SpeedCount,
  Wear,
  WearPoint,
} from '../types'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString()
}

// Same conventions as the add-component form on BikePage: a date input is
// sent as local midnight in ISO form.
function dateToIso(date: string): string {
  return new Date(`${date}T00:00:00`).toISOString()
}

function today(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

// <input type="datetime-local"> works in local "YYYY-MM-DDTHH:mm".
function nowLocalInput(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  )
}

// predicted_replacement_date is a UTC calendar date ("YYYY-MM-DD"). Format it
// in UTC so a negative local offset doesn't show the day before.
function formatUtcDate(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, {
    timeZone: 'UTC',
  })
}

const CHART_WIDTH = 600
const CHART_HEIGHT = 240
const MARGIN = { top: 12, right: 16, bottom: 28, left: 44 }
const DAY_MS = 24 * 60 * 60 * 1000

// Gridline steps to choose from, smallest first, and the minimum gap.
const GRID_STEPS = [0.25, 0.5, 1, 2, 5, 10]
const MIN_GRID_GAP_PX = 20

interface EstimateLine {
  /** Start (install) and end (today, or retirement) as epoch ms. */
  from: number
  to: number
  /** The estimate at `to`; the line starts from 0% at `from`. */
  wearPercent: number
}

// Wear (%) against date. Manual readings are separate dots; the estimate from
// ride distance is a line from install (0%) to today's estimate. Dashed lines
// mark the cassette check (half the limit) and the limit, when they're set.
function WearChart({
  points,
  estimate,
  warningPercent,
  limitPercent,
}: {
  points: WearPoint[]
  estimate: EstimateLine | null
  warningPercent: number | null
  limitPercent: number | null
}) {
  const times = points.map((p) => new Date(p.occurred_at).getTime())
  const wears = points.map((p) => Number(p.wear_percent))

  // The x range covers the readings and the estimate line. A single instant
  // is padded by a day each way so the scale isn't zero-width.
  const allTimes = estimate ? [...times, estimate.from, estimate.to] : times
  let minT = Math.min(...allTimes)
  let maxT = Math.max(...allTimes)
  if (minT === maxT) {
    minT -= DAY_MS
    maxT += DAY_MS
  }

  const plotW = CHART_WIDTH - MARGIN.left - MARGIN.right
  const plotH = CHART_HEIGHT - MARGIN.top - MARGIN.bottom

  // The top is at least 1.00 and covers everything drawn, rounded up to a
  // whole number. The step is the smallest in GRID_STEPS that keeps
  // gridlines at least MIN_GRID_GAP_PX apart once the top is rounded up to a
  // multiple of it. Wear can't pass 100%, so a step of 10 always fits.
  const wholeTop = Math.ceil(
    Math.max(1, ...wears, estimate?.wearPercent ?? 0, limitPercent ?? 0),
  )
  let step = GRID_STEPS[GRID_STEPS.length - 1]
  let maxY = Math.ceil(wholeTop / step) * step
  for (const candidate of GRID_STEPS) {
    const top = Math.ceil(wholeTop / candidate) * candidate
    if ((candidate / top) * plotH >= MIN_GRID_GAP_PX) {
      step = candidate
      maxY = top
      break
    }
  }

  const x = (t: number) => MARGIN.left + ((t - minT) / (maxT - minT)) * plotW
  const y = (w: number) => MARGIN.top + plotH - (w / maxY) * plotH

  const ticks: number[] = []
  for (let i = 0; i * step <= maxY + 1e-9; i++) ticks.push(i * step)
  const tickLabel = (v: number) => (step < 1 ? v.toFixed(2) : String(v))

  // The two lines can be only a few pixels apart, so their labels sit at
  // opposite ends of the plot: one left, one right.
  const refs: {
    value: number
    label: string
    cls: string
    labelX: number
    anchor: 'start' | 'end'
  }[] = []
  if (warningPercent !== null) {
    refs.push({
      value: warningPercent,
      label: `cassette check ${warningPercent}%`,
      cls: 'ref warn',
      labelX: MARGIN.left + 4,
      anchor: 'start',
    })
  }
  if (limitPercent !== null) {
    refs.push({
      value: limitPercent,
      label: `limit ${limitPercent}%`,
      cls: 'ref limit',
      labelX: MARGIN.left + plotW,
      anchor: 'end',
    })
  }

  return (
    <svg
      className="wear-chart"
      viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
      role="img"
      aria-label="Wear percent against date"
    >
      {ticks.map((v) => (
        <g key={v}>
          <line x1={MARGIN.left} x2={MARGIN.left + plotW} y1={y(v)} y2={y(v)} className="grid" />
          <text
            x={MARGIN.left - 6}
            y={y(v)}
            className="tick"
            textAnchor="end"
            dominantBaseline="middle"
          >
            {tickLabel(v)}
          </text>
        </g>
      ))}
      {refs.map((ref) => (
        <g key={ref.cls}>
          <line
            x1={MARGIN.left}
            x2={MARGIN.left + plotW}
            y1={y(ref.value)}
            y2={y(ref.value)}
            className={ref.cls}
            strokeDasharray="6 4"
          />
          <text x={ref.labelX} y={y(ref.value) - 4} className="tick" textAnchor={ref.anchor}>
            {ref.label}
          </text>
        </g>
      ))}
      <text x={MARGIN.left} y={CHART_HEIGHT - 8} className="tick">
        {new Date(minT).toLocaleDateString()}
      </text>
      <text x={MARGIN.left + plotW} y={CHART_HEIGHT - 8} className="tick" textAnchor="end">
        {new Date(maxT).toLocaleDateString()}
      </text>
      {estimate && (
        <line
          className="estimate"
          x1={x(estimate.from)}
          y1={y(0)}
          x2={x(estimate.to)}
          y2={y(estimate.wearPercent)}
        >
          <title>{`Estimated from rides: ${estimate.wearPercent}% on ${formatDate(
            new Date(estimate.to).toISOString(),
          )}`}</title>
        </line>
      )}
      {points.map((p, i) => (
        <circle key={i} className="point" cx={x(times[i])} cy={y(wears[i])} r={4}>
          <title>{`${formatDate(p.occurred_at)}: ${p.wear_percent}% at ${p.odometer_km} km`}</title>
        </circle>
      ))}
    </svg>
  )
}

function ReadingForm({
  component,
  onAdded,
}: {
  component: Component
  onAdded: () => void
}) {
  const [when, setWhen] = useState(nowLocalInput)
  const [odometer, setOdometer] = useState('')
  const [wear, setWear] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await createEvent(component.bike_id, {
        type: 'measurement',
        component_id: component.id,
        occurred_at: new Date(when).toISOString(),
        odometer_km: odometer,
        payload: { wear_percent: Number(wear) },
      })
      setWhen(nowLocalInput())
      setOdometer('')
      setWear('')
      onAdded()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="stacked" onSubmit={submit}>
      <h3>Record a reading</h3>
      <label>
        Date and time
        <input
          type="datetime-local"
          value={when}
          onChange={(e) => setWhen(e.target.value)}
          required
        />
      </label>
      <label>
        Odometer (km)
        <input
          type="number"
          min="0"
          step="0.01"
          value={odometer}
          onChange={(e) => setOdometer(e.target.value)}
          required
        />
      </label>
      <label>
        Wear (%)
        <input
          type="number"
          min="0"
          max="100"
          step="0.01"
          value={wear}
          onChange={(e) => setWear(e.target.value)}
          required
        />
      </label>
      {error && <p className="error">{error}</p>}
      <div>
        <button type="submit" disabled={saving}>
          {saving ? 'Saving…' : 'Save reading'}
        </button>
      </div>
    </form>
  )
}

// Mounted only while open, so its fields start from the current component.
function ReplaceForm({
  component,
  onCancel,
  onReplaced,
}: {
  component: Component
  onCancel: () => void
  onReplaced: (result: ComponentReplaceResult) => void
}) {
  const [finalOdometer, setFinalOdometer] = useState('')
  const [type, setType] = useState(component.type)
  const [brand, setBrand] = useState('')
  const [model, setModel] = useState('')
  const [installedDate, setInstalledDate] = useState(today)
  const [installedOdometer, setInstalledOdometer] = useState('')
  const [odometerEdited, setOdometerEdited] = useState(false)
  const [lifespan, setLifespan] = useState(component.lifespan_km ?? '')
  // Chain-only field, started from the old part; shown and sent only when
  // the new type is exactly "chain".
  const [speedCount, setSpeedCount] = useState<SpeedCount | ''>(component.speed_count ?? '')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const isChain = type.trim() === 'chain'

  function chooseSpeedCount(value: SpeedCount) {
    // Prefill the lifespan the API would default to; it stays editable. The
    // wear limit follows from the speed count and isn't sent.
    setSpeedCount(value)
    setLifespan(CHAIN_DEFAULTS[value].lifespanKm)
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const result = await replaceComponent(component.id, {
        old_final_odometer_km: finalOdometer,
        new: {
          type: type.trim(),
          brand: brand.trim() || null,
          model: model.trim() || null,
          installed_at: dateToIso(installedDate),
          installed_odometer_km: installedOdometer,
          lifespan_km: lifespan || null,
          ...(isChain && { speed_count: speedCount === '' ? null : speedCount }),
        },
      })
      onReplaced(result)
    } catch (e) {
      setError((e as Error).message)
      setSaving(false)
    }
  }

  return (
    <form className="stacked" onSubmit={submit}>
      <h2>Replace {component.type}</h2>
      <label>
        Old part's final odometer (km)
        <input
          type="number"
          min="0"
          step="0.01"
          value={finalOdometer}
          onChange={(e) => {
            setFinalOdometer(e.target.value)
            // Usually the new part goes on at the same reading.
            if (!odometerEdited) setInstalledOdometer(e.target.value)
          }}
          required
        />
      </label>
      <label>
        New part type
        <input
          value={type}
          onChange={(e) => setType(e.target.value)}
          required
          maxLength={50}
        />
      </label>
      <label>
        Brand
        <input value={brand} onChange={(e) => setBrand(e.target.value)} maxLength={100} />
      </label>
      <label>
        Model
        <input value={model} onChange={(e) => setModel(e.target.value)} maxLength={100} />
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
          value={installedOdometer}
          onChange={(e) => {
            setInstalledOdometer(e.target.value)
            setOdometerEdited(true)
          }}
          required
        />
      </label>
      {isChain && (
        <ChainFields speedCount={speedCount} onSpeedCount={chooseSpeedCount} />
      )}
      <label>
        {isChain ? 'Lifespan (km)' : 'Lifespan (km, optional)'}
        <input
          type="number"
          min="0.01"
          step="0.01"
          value={lifespan}
          onChange={(e) => setLifespan(e.target.value)}
          required={isChain}
        />
      </label>
      {error && <p className="error">{error}</p>}
      <div>
        <button type="submit" disabled={saving}>
          {saving ? 'Replacing…' : 'Replace'}
        </button>{' '}
        <button type="button" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </form>
  )
}

export default function ComponentPage() {
  const componentId = Number(useParams().componentId)
  const navigate = useNavigate()
  const [replacing, setReplacing] = useState(false)

  const [component, setComponent] = useState<Component | null>(null)
  const [mileage, setMileage] = useState<Mileage | null>(null)
  const [wear, setWear] = useState<Wear | null>(null)
  // When the wear data was fetched: the "today" end of the estimate line.
  const [wearLoadedAt, setWearLoadedAt] = useState(0)
  const [bike, setBike] = useState<Bike | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let ignore = false
    // The bike id comes from the component, so the bike is fetched after it.
    getComponent(componentId)
      .then((componentData) =>
        Promise.all([
          componentData,
          getMileage(componentId),
          getWear(componentId),
          getBike(componentData.bike_id),
        ]),
      )
      .then(([componentData, mileageData, wearData, bikeData]) => {
        if (!ignore) {
          setComponent(componentData)
          setMileage(mileageData)
          setWear(wearData)
          setWearLoadedAt(Date.now())
          setBike(bikeData)
          setError(null)
        }
      })
      .catch((e: Error) => {
        if (!ignore) setError(e.message)
      })
    return () => {
      ignore = true
    }
  }, [componentId, reload])

  async function retire() {
    if (!component || !window.confirm(`Retire this ${component.type}?`)) return
    try {
      await retireComponent(componentId)
      setReload((n) => n + 1)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function refreshWear() {
    try {
      setWear(await getWear(componentId))
      setWearLoadedAt(Date.now())
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (!component || !mileage || !wear || !bike) {
    return error ? <p className="error">{error}</p> : <p>Loading…</p>
  }

  const retired = component.retired_at !== null
  const archived = bike.archived_at !== null
  const isChain = component.type === 'chain'
  const latest = wear.points.length > 0 ? wear.points[wear.points.length - 1] : null
  // The estimate runs from install (0%) to today, or to retirement, after
  // which no more rides count.
  const estimateLine =
    wear.estimated_wear_percent === null
      ? null
      : {
          from: new Date(component.installed_at).getTime(),
          to: component.retired_at ? new Date(component.retired_at).getTime() : wearLoadedAt,
          wearPercent: Number(wear.estimated_wear_percent),
        }

  return (
    <section>
      <p>
        <Link to={`/bikes/${component.bike_id}`}>← Back to bike</Link>
      </p>
      <h1>
        {component.type}
        {retired && <span className="badge">retired</span>}
      </h1>
      {error && <p className="error">{error}</p>}

      <dl className="details">
        <dt>Brand</dt>
        <dd>{component.brand ?? '—'}</dd>
        <dt>Model</dt>
        <dd>{component.model ?? '—'}</dd>
        <dt>Installed</dt>
        <dd>{formatDate(component.installed_at)}</dd>
        <dt>Installed odometer</dt>
        <dd>{component.installed_odometer_km} km</dd>
        <dt>Lifespan</dt>
        <dd>{component.lifespan_km ? `${component.lifespan_km} km` : '—'}</dd>
        {isChain && (
          <>
            <dt>Speed count</dt>
            <dd>
              {component.speed_count === null ? '—' : SPEED_COUNT_LABELS[component.speed_count]}
            </dd>
          </>
        )}
        <dt>Retired</dt>
        <dd>
          {component.retired_at ? formatDate(component.retired_at) : '—'}
          {component.retired_odometer_km !== null &&
            ` at ${component.retired_odometer_km} km`}
        </dd>
        <dt>Mileage</dt>
        <dd>{mileage.distance_km} km</dd>
      </dl>

      <h2>Wear</h2>
      {isChain && wear.cassette_warning && (
        <p className="warning" role="status">
          Chain stretch is at or above {wear.cassette_warning_percent}%. Check the
          cassette before the chain goes further.
        </p>
      )}
      {!isChain ? (
        // Non-chains have no estimate; their readings are shown as-is.
        <p>
          Latest reading: <strong>{latest ? `${latest.wear_percent}%` : 'no readings'}</strong>
          {' · '}Limit: <strong>{wear.wear_limit_percent}%</strong>
        </p>
      ) : estimateLine === null ? (
        <p>
          Estimated wear: <strong>set speed count and life</strong>
        </p>
      ) : (
        <p>
          Estimated wear: <strong>{wear.estimated_wear_percent}%</strong>
          {' · '}Limit: <strong>{wear.wear_limit_percent}%</strong>
          {' · '}Estimated remaining: <strong>{wear.estimated_km_remaining} km</strong>
          {' · '}Predicted replacement:{' '}
          <strong>
            {wear.predicted_replacement_date === null
              ? 'not enough data'
              : formatUtcDate(wear.predicted_replacement_date)}
          </strong>
        </p>
      )}
      {wear.points.length === 0 && estimateLine === null ? (
        <p>No wear measurements yet.</p>
      ) : (
        <WearChart
          points={wear.points}
          estimate={estimateLine}
          warningPercent={
            wear.cassette_warning_percent === null ? null : Number(wear.cassette_warning_percent)
          }
          limitPercent={
            wear.wear_limit_percent === null ? null : Number(wear.wear_limit_percent)
          }
        />
      )}
      {(wear.points.length > 0 || estimateLine !== null) && (
        <p className="chart-legend">
          {estimateLine !== null && 'Line: estimated from rides. '}
          {wear.points.length > 0 && 'Dots: manual readings.'}
        </p>
      )}
      {wear.points.length > 0 && (
        <>
          <table>
            <thead>
              <tr>
                <th>Date and time</th>
                <th>Odometer (km)</th>
                <th>Wear (%)</th>
              </tr>
            </thead>
            <tbody>
              {/* The API returns oldest first; the table shows newest first. */}
              {[...wear.points].reverse().map((p, i) => (
                <tr key={i}>
                  <td>{new Date(p.occurred_at).toLocaleString()}</td>
                  <td>{p.odometer_km}</td>
                  <td>{p.wear_percent}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {!retired && !archived && <ReadingForm component={component} onAdded={refreshWear} />}

      {!retired && !replacing && (
        <p>
          <button type="button" onClick={() => setReplacing(true)}>
            Replace
          </button>{' '}
          <button type="button" onClick={retire}>
            Retire component
          </button>
        </p>
      )}
      {!retired && replacing && (
        <ReplaceForm
          component={component}
          onCancel={() => setReplacing(false)}
          onReplaced={(result) => {
            setReplacing(false)
            navigate(`/components/${result.new.id}`)
          }}
        />
      )}
    </section>
  )
}
