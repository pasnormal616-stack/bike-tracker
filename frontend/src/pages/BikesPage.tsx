import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { createBike, listBikes } from '../api'
import type { Bike } from '../types'

export default function BikesPage() {
  const [bikes, setBikes] = useState<Bike[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let ignore = false
    listBikes()
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
                <Link to={`/bikes/${bike.id}`}>{bike.name}</Link>
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
