// Foto importate da galleria/file: ridimensionamento a 1600 px nel telefono (upload più veloce).

export const MAX_SIDE = 1600

/** Se l'utente sceglie più foto del massimo, ne tengo una selezione uniforme (come nel benchmark). */
export function subsample<T>(items: T[], max: number): T[] {
  if (items.length <= max) return items
  return Array.from({ length: max }, (_, i) => items[Math.round((i * (items.length - 1)) / (max - 1))])
}

export function fitSize(w: number, h: number, maxSide = MAX_SIDE): { width: number; height: number } {
  const s = Math.min(1, maxSide / Math.max(w, h))
  return { width: Math.round(w * s), height: Math.round(h * s) }
}

/** Ridimensiona rispettando l'orientamento EXIF. Se il browser non decodifica il formato
 *  (es. HEIC su Android), invia il file originale: il server lo converte. */
export async function resizeImageFile(file: File, maxSide = MAX_SIDE): Promise<Blob> {
  let bmp: ImageBitmap
  try {
    bmp = await createImageBitmap(file, { imageOrientation: 'from-image' })
  } catch {
    return file
  }
  const { width, height } = fitSize(bmp.width, bmp.height, maxSide)
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  canvas.getContext('2d')!.drawImage(bmp, 0, 0, width, height)
  bmp.close()
  return new Promise((resolve) => canvas.toBlob(b => resolve(b ?? file), 'image/jpeg', 0.88))
}
