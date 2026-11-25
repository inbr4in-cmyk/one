/** Built-in names of the system funnel stages. A stage the school renamed in Справочники shows the school's name, not the translation. */
const BUILT_IN: Record<string, string> = {
  new: 'Новая заявка', contacted: 'Связались', trial_booked: 'Записан на пробный', trial_done: 'Пришёл на пробный',
  paid: 'Оплатил', lost: 'Отказ', left: 'Ушёл', agreed: 'Договорились',
}
export const stageRenamed = (code: string | null | undefined, name: string | null | undefined): boolean =>
  !!code && !!name && BUILT_IN[code] !== undefined && BUILT_IN[code] !== name
