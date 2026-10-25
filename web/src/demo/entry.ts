/**
 * Entry point of the offline demo build (`npm run build:demo`). The clock goes first so every module
 * that reads "now" sees the day the fixtures were recorded; then the regular app boots.
 */
import './clock'
import './fonts/fonts.css'
import './demo.css'
import type { Component } from 'vue'
import type { DemoHooks } from '@/api/http'
import { demoDownload, demoRequest, demoRestore } from './server'
import DemoLogin from './DemoLogin.vue'

const hooks: DemoHooks = { request: demoRequest, restore: demoRestore, download: demoDownload }
Object.assign(globalThis as { __oeDemo?: DemoHooks; __oeDemoLogin?: Component }, { __oeDemo: hooks, __oeDemoLogin: DemoLogin })

// The app itself, after the hooks are in place.
await import('../main')

const badge = document.createElement('div')
badge.className = 'demo-badge'
badge.textContent = 'Демо'
badge.title = 'Демо-версия: данные примерные, изменения не сохраняются'
badge.setAttribute('aria-hidden', 'true')
document.body.appendChild(badge)
