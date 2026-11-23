import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getComponent, getMileage, getWear, retireComponent } from '../api'
import type { Component, Mileage, Wear } from '../types'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString()
}

export default function ComponentPage() {
  const componentId = Number(useParams().componentId)

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
        <dd>{component.retired_at ? formatDate(component.retired_at) : '—'}</dd>
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

      {!retired && (
        <button type="button" onClick={retire}>
          Retire component
        </button>
      )}
    </section>
  )
}
