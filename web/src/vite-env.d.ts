/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** '1' only in the offline demo build (`npm run build:demo`). */
  readonly VITE_DEMO?: string
}
