import { useEffect, useState, type FormEvent } from 'react'
import { listTorque, setTorque } from './api'
import type { BoltTorque } from './types'

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString()
}

/** Each bolt's current torque, its history in a collapsible list, and a form
 * to set a value. readOnly hides the form (archived bike). */
export default function TorqueSection({
  componentId,
  readOnly,
}: {
  componentId: number
  readOnly: boolean
}) {
  const [bolts, setBolts] = useState<BoltTorque[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [bolt, setBolt] = useState('')
  const [value, setValue] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let ignore = false
    listTorque(componentId)
      .then((data) => {
        if (!ignore) {
          setBolts(data)
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

  async function save(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await setTorque(componentId, bolt.trim(), value)
      setBolt('')
      setValue('')
      setError(null)
      setReload((n) => n + 1)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <h2>Torque specs</h2>
      {error && <p className="error">{error}</p>}
      {bolts === null && !error && <p>Loading…</p>}
      {bolts !== null &&
        (bolts.length === 0 ? (
          <p>No torque values yet.</p>
        ) : (
          <ul>
            {bolts.map((b) => (
              <li key={b.bolt}>
                {b.bolt}: <strong>{b.current.torque_nm} Nm</strong>
                {b.history.length > 1 && (
                  <details>
                    <summary>History ({b.history.length} values)</summary>
                    <ul>
                      {b.history.map((h) => (
                        <li key={h.id}>
                          {h.torque_nm} Nm, set {formatDateTime(h.created_at)}
                          {h.deleted_at ? `, replaced ${formatDateTime(h.deleted_at)}` : ' (current)'}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </li>
            ))}
          </ul>
        ))}
      {!readOnly && (
        <form className="stacked" onSubmit={save}>
          <label>
            Bolt
            <input
              value={bolt}
              onChange={(e) => setBolt(e.target.value)}
              placeholder="Steerer clamp"
              required
              maxLength={60}
              list={`torque-bolts-${componentId}`}
            />
          </label>
          {/* Suggests existing bolts, so a new value goes to the same bolt. */}
          <datalist id={`torque-bolts-${componentId}`}>
            {bolts?.map((b) => <option key={b.bolt} value={b.bolt} />)}
          </datalist>
          <label>
            Torque (Nm)
            <input
              type="number"
              min="0.01"
              max="9999.99"
              step="0.01"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              required
            />
          </label>
          <div>
            <button type="submit" disabled={saving}>
              {saving ? 'Saving…' : 'Save torque value'}
            </button>
          </div>
        </form>
      )}
    </>
  )
}
