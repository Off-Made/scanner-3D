// Tipi delle modifiche al modello, separati da three.js: così l'archivio e la Home
// non caricano la libreria 3D (avvio più veloce sui telefoni di fascia media).
export type Axis = 'x' | 'y' | 'z'

export interface Edit {
  /** matrice di rotazione 3x3 (righe), composta da rotazioni di 90° */
  rot: number[]
  /** fattore di scala uniforme rispetto al modello ricevuto dal server */
  scale: number
  /** true quando l'utente ha impostato una misura reale */
  realScale: boolean
}

export const IDENTITY_EDIT: Edit = { rot: [1, 0, 0, 0, 1, 0, 0, 0, 1], scale: 1, realScale: false }
