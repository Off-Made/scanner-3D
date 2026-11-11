// Accesso alla fotocamera posteriore con gestione delle differenze iOS / Android.

export type Platform = 'ios' | 'android' | 'other'
export type Browser = 'safari' | 'chrome' | 'samsung' | 'firefox' | 'other'

export function detectPlatform(ua = navigator.userAgent, maxTouch = navigator.maxTouchPoints): Platform {
  if (/iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && maxTouch > 1)) return 'ios' // iPadOS si presenta come Mac
  if (/Android/.test(ua)) return 'android'
  return 'other'
}

export function detectBrowser(ua = navigator.userAgent): Browser {
  if (/SamsungBrowser/.test(ua)) return 'samsung'
  if (/CriOS|Chrome/.test(ua)) return 'chrome'
  if (/FxiOS|Firefox/.test(ua)) return 'firefox'
  if (/Safari/.test(ua)) return 'safari'
  return 'other'
}

export interface CameraProblem { title: string; message: string; steps?: string[] }

/** Traduce gli errori di getUserMedia in istruzioni comprensibili, diverse per piattaforma. */
export function describeCameraError(err: unknown, platform: Platform, browser: Browser, secure: boolean): CameraProblem {
  if (!secure) {
    return {
      title: 'Serve una connessione sicura',
      message: 'Il browser permette la fotocamera solo su pagine HTTPS. Apri l’app dall’indirizzo https:// che ti è stato fornito.',
    }
  }
  const name = (err as { name?: string })?.name ?? ''
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    const steps =
      platform === 'ios'
        ? ['Apri Impostazioni › Safari › Fotocamera e scegli “Chiedi” o “Consenti”.',
           'Oppure tocca “aA” nella barra degli indirizzi › Impostazioni sito web › Fotocamera.',
           'Se usi l’app dalla schermata Home, chiudila e riaprila dopo aver cambiato il permesso.']
        : browser === 'samsung'
          ? ['Tocca il lucchetto accanto all’indirizzo › Autorizzazioni › Fotocamera › Consenti.',
             'Verifica anche Impostazioni Android › App › Samsung Internet › Autorizzazioni › Fotocamera.']
          : platform === 'android'
            ? ['Tocca il lucchetto accanto all’indirizzo › Autorizzazioni › Fotocamera › Consenti.',
               'Verifica anche Impostazioni Android › App › Chrome › Autorizzazioni › Fotocamera.']
            : ['Consenti l’accesso alla fotocamera dalle impostazioni del sito nel browser.']
    return { title: 'Permesso fotocamera negato', message: 'Per scansionare serve l’accesso alla fotocamera.', steps }
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError') {
    return { title: 'Fotocamera non trovata', message: 'Non è stata trovata una fotocamera posteriore utilizzabile su questo dispositivo.' }
  }
  if (name === 'NotReadableError' || name === 'AbortError') {
    return {
      title: 'Fotocamera occupata',
      message: 'Un’altra app sta usando la fotocamera. Chiudila (videochiamate, app Fotocamera) e riprova.',
    }
  }
  if (name === 'TypeError' || typeof navigator === 'undefined' || !navigator.mediaDevices) {
    return { title: 'Browser non supportato', message: 'Questo browser non permette l’accesso alla fotocamera. Usa Safari su iPhone o Chrome / Samsung Internet su Android.' }
  }
  return { title: 'Errore fotocamera', message: `Non è stato possibile avviare la fotocamera (${name || 'errore sconosciuto'}).` }
}

/** Avvia la fotocamera posteriore. Va chiamata da un gesto dell'utente (tap) per compatibilità iOS. */
export async function startRearCamera(video: HTMLVideoElement): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) throw new TypeError('getUserMedia non disponibile')
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: {
      facingMode: { ideal: 'environment' },
      width: { ideal: 1920 },
      height: { ideal: 1440 },
    },
  })
  // iOS: senza playsinline + muted il video va a schermo intero o non parte
  video.setAttribute('playsinline', '')
  video.muted = true
  video.srcObject = stream
  await video.play()
  return stream
}

export function stopStream(stream: MediaStream | null) {
  stream?.getTracks().forEach(t => t.stop())
}

/** Cattura un fotogramma ridimensionato (lato lungo = maxSide) come JPEG. Safari non ha ImageCapture. */
export async function captureFrame(video: HTMLVideoElement, maxSide = 2400, quality = 0.92): Promise<Blob> {
  const { videoWidth: w, videoHeight: h } = video
  if (!w || !h) throw new Error('Video non ancora pronto')
  const scale = Math.min(1, maxSide / Math.max(w, h))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(w * scale)
  canvas.height = Math.round(h * scale)
  canvas.getContext('2d')!.drawImage(video, 0, 0, canvas.width, canvas.height)
  return new Promise((resolve, reject) =>
    canvas.toBlob(b => (b ? resolve(b) : reject(new Error('Conversione JPEG fallita'))), 'image/jpeg', quality))
}

type OrientationPermission = 'granted' | 'denied' | 'not-required' | 'unsupported'

/** Giroscopio: su iOS 13+ serve un permesso esplicito chiesto da un tap; su Android no. */
export async function requestOrientationPermission(): Promise<OrientationPermission> {
  if (typeof DeviceOrientationEvent === 'undefined') return 'unsupported'
  const req = (DeviceOrientationEvent as unknown as { requestPermission?: () => Promise<'granted' | 'denied'> }).requestPermission
  if (typeof req !== 'function') return 'not-required'
  try { return await req() } catch { return 'denied' }
}
