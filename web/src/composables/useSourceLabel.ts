import { useI18n } from 'vue-i18n'
import { useSourcesStore } from '@/stores/sources'

/** Lead/student source label: the name from the Справочники list, else the built-in translation, else as-is. */
export function useSourceLabel() {
  const { t, te } = useI18n()
  const sources = useSourcesStore()
  void sources.load()
  return (s: string | null | undefined) =>
    !s ? '' : sources.byCode.get(s)?.name ?? (te(`crm.source.${s}`) ? t(`crm.source.${s}`) : s)
}
