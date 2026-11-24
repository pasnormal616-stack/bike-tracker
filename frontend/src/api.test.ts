import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { downloadServiceHistory, getBike, listBikes } from './api'

// Vitest runs in Node, which has no localStorage, so give each test a
// fresh in-memory one.
function memoryStorage(): Storage {
  const items = new Map<string, string>()
  return {
    get length() {
      return items.size
    },
    clear: () => items.clear(),
    getItem: (key) => items.get(key) ?? null,
    key: (index) => [...items.keys()][index] ?? null,
    removeItem: (key) => {
      items.delete(key)
    },
    setItem: (key, value) => {
      items.set(key, String(value))
    },
  }
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('api client', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', memoryStorage())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends the x-user-id header from localStorage', async () => {
    localStorage.setItem('userId', '42')
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([], 200))
    vi.stubGlobal('fetch', fetchMock)

    await listBikes()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/bikes$/)
    expect(new Headers(init.headers).get('x-user-id')).toBe('42')
  })

  it('throws an error containing the status on a 404', async () => {
    localStorage.setItem('userId', '42')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: 'Bike not found' }, 404)),
    )

    const result = getBike(999)

    await expect(result).rejects.toThrow('404')
    await expect(result).rejects.toThrow('Bike not found')
  })

  it('downloads the service history with the header and reads the file name', async () => {
    localStorage.setItem('userId', '42')
    const pdfBytes = new TextEncoder().encode('%PDF-1.4 test')
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(pdfBytes, {
        status: 200,
        headers: {
          'Content-Type': 'application/pdf',
          'Content-Disposition':
            'attachment; filename="service-history-road-bike-2026-11-24.pdf"',
        },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await downloadServiceHistory(7, '2026-03-01', '2026-03-31')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/bikes\/7\/service-history\.pdf\?from=2026-03-01&to=2026-03-31$/)
    expect(new Headers(init.headers).get('x-user-id')).toBe('42')
    expect(result.filename).toBe('service-history-road-bike-2026-11-24.pdf')
    expect(await result.blob.text()).toBe('%PDF-1.4 test')
  })
})
