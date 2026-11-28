import { http, qs } from './http'

export interface AdTotals { spend: number; impressions: number; reach: number; clicks: number; link_clicks: number; results: number; ctr: number; cpc: number | null }
export interface AdsReport {
  /** the key is entered on the server; without it there is nothing to read */
  configured: boolean
  period: [string, string]
  /** the ad account's currency, e.g. USD */
  currency: string
  synced_at: string | null
  total: AdTotals
  /** leads of the period that came from Instagram and WhatsApp, and how many of them paid */
  crm: { leads: number; paid: number; cost_per_lead: number | null; cost_per_paid: number | null }
  days: (AdTotals & { day: string })[]
  campaigns: (AdTotals & { id: string; name: string })[]
}

export const adsApi = {
  report: (p: { date_from: string; date_to: string }) => http.get<AdsReport>(`/ads/report${qs(p)}`),
  sync: () => http.post<{ ok: boolean; rows?: number }>('/ads/sync'),
}
