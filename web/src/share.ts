// Condivisione del file: foglio di condivisione nativo (AirDrop / app su iOS, Android) se il
// browser lo supporta, altrimenti download classico.

export type ShareResult = 'shared' | 'downloaded' | 'cancelled'

export function canShareFiles(): boolean {
  try {
    const f = new File([new Uint8Array(1)], 'test.stl', { type: 'application/octet-stream' })
    return typeof navigator.canShare === 'function' && navigator.canShare({ files: [f] })
  } catch { return false }
}

export async function shareFile(blob: Blob, name: string): Promise<ShareResult> {
  // iOS non riconosce i tipi "model/*": con octet-stream la condivisione funziona con tutte le app
  const file = new File([blob], name, { type: 'application/octet-stream' })
  if (typeof navigator.canShare === 'function' && navigator.canShare({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: name })
      return 'shared'
    } catch (e) {
      if ((e as Error).name === 'AbortError') return 'cancelled'
      // NotAllowedError ecc.: ripiego sul download
    }
  }
  downloadFile(blob, name)
  return 'downloaded'
}

export function downloadFile(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 30_000)
}
