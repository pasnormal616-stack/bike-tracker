import { useState } from 'react'
import { DELETE_CONFIRMATION, USER_ID_KEY, deleteMyAccount, exportMyData } from './api'
import { saveBlob } from './download'

/** Export all of the user's data, or delete the account. onDeleted runs
 * after the account is gone and the stored user id is cleared. */
export default function PrivacySection({ onDeleted }: { onDeleted: () => void }) {
  const [exporting, setExporting] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function exportData() {
    setExporting(true)
    setError(null)
    try {
      const { blob, filename } = await exportMyData()
      saveBlob(blob, filename)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setExporting(false)
    }
  }

  async function deleteAccount() {
    setDeleting(true)
    setError(null)
    try {
      await deleteMyAccount()
      localStorage.removeItem(USER_ID_KEY)
      onDeleted()
    } catch (e) {
      setError((e as Error).message)
      setDeleting(false)
    }
  }

  function cancel() {
    setConfirming(false)
    setConfirmText('')
  }

  return (
    <>
      <h2>Privacy</h2>
      {error && <p className="error">{error}</p>}
      <p>
        <button type="button" onClick={exportData} disabled={exporting}>
          {exporting ? 'Exporting…' : 'Export my data'}
        </button>{' '}
        {!confirming && (
          <button type="button" onClick={() => setConfirming(true)}>
            Delete my account
          </button>
        )}
      </p>
      {confirming && (
        <div className="stacked">
          <p className="warning">
            This permanently deletes your account and all your bikes, components, rides, events,
            reminders, torque specs and setup logs. It can't be undone.
          </p>
          <label>
            Type {DELETE_CONFIRMATION} to confirm
            <input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              autoComplete="off"
            />
          </label>
          <div>
            <button
              type="button"
              onClick={deleteAccount}
              disabled={confirmText !== DELETE_CONFIRMATION || deleting}
            >
              {deleting ? 'Deleting…' : 'Delete my account'}
            </button>{' '}
            <button type="button" onClick={cancel} disabled={deleting}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </>
  )
}
