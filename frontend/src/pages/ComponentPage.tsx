import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  getComponent,
  getMileage,
  getWear,
  replaceComponent,
  retireComponent,
} from '../api'
import type { Component, ComponentReplaceResult, Mileage, Wear } from '../types'

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
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

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
      <label>
        Lifespan (km, optional)
        <input
          type="number"
          min="0.01"
          step="0.01"
          value={lifespan}
          onChange={(e) => setLifespan(e.target.value)}
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
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let ignore = false
    Promise.all([
      getComponent(componentId),
      getMileage(componentId),
      getWear(componentId),
    ])
      .then(([componentData, mileageData, wearData]) => {
        if (!ignore) {
          setComponent(componentData)
          setMileage(mileageData)
          setWear(wearData)
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

  if (!component || !mileage || !wear) {
    return error ? <p className="error">{error}</p> : <p>Loading…</p>
  }

  const retired = component.retired_at !== null

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
      {wear.points.length === 0 ? (
        <p>No wear measurements yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Odometer (km)</th>
              <th>Wear (%)</th>
            </tr>
          </thead>
          <tbody>
            {wear.points.map((p, i) => (
              <tr key={i}>
                <td>{formatDate(p.occurred_at)}</td>
                <td>{p.odometer_km}</td>
                <td>{p.wear_percent}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p>
        Estimated remaining before {wear.wear_limit_percent}% wear:{' '}
        <strong>
          {wear.estimated_km_remaining === null
            ? 'not enough data'
            : `${wear.estimated_km_remaining} km`}
        </strong>
      </p>

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
