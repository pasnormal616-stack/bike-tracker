// Saves a downloaded file through a temporary object URL. The blob was
// fetched with the x-user-id header, so no plain link to the API is used.
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Revoked on the next tick, once the browser has started the download.
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
