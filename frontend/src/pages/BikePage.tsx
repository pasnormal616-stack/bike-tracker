import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { addComponent, archiveBike, getBike, listComponents } from '../api'
import type { Bike, Component } from '../types'

// A date input gives "YYYY-MM-DD"; store it as local midnight in ISO form,
// so rides later that day count toward the component's mileage.
function dateToIso(date: string): string {
  return new Date(`${date}T00:00:00`).toISOString()
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

  return (
    <section>
      <p>
        <Link to="/">← All bikes</Link>
      </p>
      <h1>
        {bike.name}
        {archived && <span className="badge">archived</span>}
      </h1>
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
    </section>
  )
}
