import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { addSetupChange, deleteSetupLog, getBike, getSetupLog } from '../api'
import type { Bike, SetupLogDetail } from '../types'

const PAGE_SIZE = 50

// Blank means "no value" (null), e.g. a part that wasn't fitted before.
function valueOrNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

function ChangeForm({ setupId, onAdded }: { setupId: number; onAdded: () => void }) {
  const [field, setField] = useState('')
  const [oldValue, setOldValue] = useState('')
  const [newValue, setNewValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await addSetupChange(setupId, {
        field: field.trim(),
        old_value: valueOrNull(oldValue),
        new_value: valueOrNull(newValue),
      })
      setField('')
      setOldValue('')
      setNewValue('')
      setError(null)
      onAdded()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <h2>Record a change</h2>
      <form className="stacked" onSubmit={save}>
        <label>
          Setting
          <input
            value={field}
            onChange={(e) => setField(e.target.value)}
            placeholder="Tyre pressure (rear)"
            required
            maxLength={60}
          />
        </label>
        <label>
          Old value (optional)
          <input value={oldValue} onChange={(e) => setOldValue(e.target.value)} maxLength={500} />
        </label>
        <label>
          New value (optional)
          <input value={newValue} onChange={(e) => setNewValue(e.target.value)} maxLength={500} />
        </label>
        {error && <p className="error">{error}</p>}
        <div>
          <button type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Record change'}
          </button>
        </div>
      </form>
    </>
  )
}

export default function SetupPage() {
  const setupId = Number(useParams().setupId)
  const navigate = useNavigate()
  const [setup, setSetup] = useState<SetupLogDetail | null>(null)
  const [bike, setBike] = useState<Bike | null>(null)
  const [offset, setOffset] = useState(0)
  const [reload, setReload] = useState(0)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    getSetupLog(setupId, PAGE_SIZE, offset)
      .then((data) => Promise.all([data, getBike(data.bike_id)]))
      .then(([data, bikeData]) => {
        if (!ignore) {
          setSetup(data)
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
  }, [setupId, offset, reload])

  async function remove() {
    if (!setup || !window.confirm(`Delete the setup log "${setup.name}"?`)) return
    try {
      await deleteSetupLog(setupId)
      navigate(`/bikes/${setup.bike_id}`)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  // After a new change, jump to the last page so it's visible.
  function showLatest() {
    if (!setup) return
    const total = setup.total_changes + 1
    setOffset(Math.floor((total - 1) / PAGE_SIZE) * PAGE_SIZE)
    setReload((n) => n + 1)
  }

  if (!setup || !bike) {
    return error ? <p className="error">{error}</p> : <p>Loading…</p>
  }

  const archived = bike.archived_at !== null
  const first = setup.total_changes === 0 ? 0 : offset + 1
  const last = offset + setup.changes.length

  return (
    <section>
      <p>
        <Link to={`/bikes/${setup.bike_id}`}>← Back to {bike.name}</Link>
      </p>
      <h1>{setup.name}</h1>
      <p>Created {new Date(setup.created_at).toLocaleString()}</p>
      {error && <p className="error">{error}</p>}

      <h2>Changes</h2>
      {setup.total_changes === 0 ? (
        <p>No changes recorded yet.</p>
      ) : (
        <>
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Setting</th>
                <th>Old</th>
                <th>New</th>
              </tr>
            </thead>
            <tbody>
              {/* Oldest first, as the API returns them. */}
              {setup.changes.map((c) => (
                <tr key={c.id}>
                  <td>{new Date(c.changed_at).toLocaleString()}</td>
                  <td>{c.field}</td>
                  <td>{c.old_value ?? '—'}</td>
                  <td>{c.new_value ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            Showing {first}–{last} of {setup.total_changes}{' '}
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </button>{' '}
            <button
              type="button"
              disabled={last >= setup.total_changes}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </button>
          </p>
        </>
      )}

      {!archived && (
        <>
          <ChangeForm setupId={setupId} onAdded={showLatest} />
          <p>
            <button type="button" onClick={remove}>
              Delete setup log
            </button>
          </p>
        </>
      )}
    </section>
  )
}
