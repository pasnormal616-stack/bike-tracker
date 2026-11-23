import { useState, type FormEvent } from 'react'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { USER_ID_KEY } from './api'
import BikePage from './pages/BikePage'
import BikesPage from './pages/BikesPage'
import ComponentPage from './pages/ComponentPage'

function readUserId(): string {
  try {
    return localStorage.getItem(USER_ID_KEY) ?? ''
  } catch {
    return ''
  }
}

export default function App() {
  const [userId, setUserId] = useState(readUserId)
  const [draft, setDraft] = useState(userId)

  function saveUserId(event: FormEvent) {
    event.preventDefault()
    const value = draft.trim()
    if (value) {
      localStorage.setItem(USER_ID_KEY, value)
    } else {
      localStorage.removeItem(USER_ID_KEY)
    }
    setUserId(value)
  }

  return (
    <BrowserRouter>
      <header className="topbar">
        <strong className="app-name">Bike Tracker</strong>
        <Link to="/">Home</Link>
        <form className="user-form" onSubmit={saveUserId}>
          <label>
            User id{' '}
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              inputMode="numeric"
              size={6}
            />
          </label>
          <button type="submit">Save</button>
        </form>
      </header>
      <main>
        {/* Keyed on the user id so every page reloads its data on switch. */}
        <Routes key={userId}>
          <Route path="/" element={<BikesPage />} />
          <Route path="/bikes/:bikeId" element={<BikePage />} />
          <Route path="/components/:componentId" element={<ComponentPage />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
