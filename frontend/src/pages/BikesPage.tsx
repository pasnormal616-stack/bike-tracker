import { useEffect, useState, type CSSProperties, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { createBike, listBikeHealth } from '../api'
import type { BikeHealth, BikeStatus } from '../types'

const STATUS_LABELS: Record<BikeStatus, string> = {
  overdue: 'Overdue',
  due_soon: 'Due soon',
  good: 'Good',
  no_lifespan: 'No lifespan set',
  no_components: 'No components',
}

// Inline so index.css stays unchanged. Overdue and due soon differ in both
// colour and weight, so they stay distinguishable without colour.
const STATUS_STYLES: Partial<Record<BikeStatus, CSSProperties>> = {
  overdue: { color: 'var(--error)', fontWeight: 700 },
  due_soon: { color: '#b45309', fontStyle: 'italic' },
}

function StatusLabel({ bike }: { bike: BikeHealth }) {
  return (
    <span style={STATUS_STYLES[bike.status] ?? { color: 'var(--muted)' }}>
      {STATUS_LABELS[bike.status]}
      {bike.due_count > 0 && ` · ${bike.due_count} due`}
    </span>
  )
}

export default function BikesPage() {
  const [bikes, setBikes] = useState<BikeHealth[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let ignore = false
    listBikeHealth()
      .then((data) => {
        if (!ignore) {
          setBikes(data)
          setError(null)
        }
      })
      .catch((e: Error) => {
        if (!ignore) setError(e.message)
      })
    return () => {
      ignore = true
    }
  }, [reload])

  async function addBike(event: FormEvent) {
    event.preventDefault()
    try {
      await createBike(name.trim())
      setName('')
      setReload((n) => n + 1)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <section>
      <h1>Bikes</h1>
      {error && <p className="error">{error}</p>}
      {bikes === null && !error && <p>Loading…</p>}
      {bikes !== null &&
        (bikes.length === 0 ? (
          <p>No bikes yet.</p>
        ) : (
          <ul>
            {bikes.map((bike) => (
              <li key={bike.id}>
                <Link to={`/bikes/${bike.id}`}>{bike.name}</Link> —{' '}
                <StatusLabel bike={bike} />
              </li>
            ))}
          </ul>
        ))}

      <h2>Add a bike</h2>
      <form onSubmit={addBike}>
        <label>
          Name{' '}
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={120}
          />
        </label>{' '}
        <button type="submit">Add</button>
      </form>
    </section>
  )
}
