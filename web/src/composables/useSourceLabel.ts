import { useI18n } from 'vue-i18n'

/** Lead/student source label. Sources are free strings on the server, so unknown ones show as-is. */
export function useSourceLabel() {
  const { t, te } = useI18n()
  return (s: string | null | undefined) => (!s ? '' : te(`crm.source.${s}`) ? t(`crm.source.${s}`) : s)
}
