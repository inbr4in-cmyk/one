<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { UiButton, UiCard, UiEmptyState, UiIcon, UiInput, UiSkeleton, UiSwitch, UiTextarea } from '@/components/ui'
import { chatsApi } from '@/api/chats'
import { profileApi, type ProfileAward, type ProfilePlace, type StaffProfile } from '@/api/profile'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { formatPhone } from '@/utils/phone'

/** Staff profile (анкета). The same page serves staff (/staff/:id) and the cabinet (/portal/teachers/:id). */
const { t, te } = useI18n()
const route = useRoute()
const auth = useAuthStore()
const toast = useToastStore()

const id = computed(() => Number(route.params.id))
const p = ref<StaffProfile | null>(null)
const failed = ref(false)
const editing = ref(false)
const saving = ref(false)
const busy = ref(false)

type PlaceForm = { place: string; role: string; year_from: string; year_to: string }
type AwardForm = { title: string; year: string; file_key: string | null; file_name: string | null }
const form = ref({ photo_key: null as string | null, photo_url: null as string | null, email: '', about: '', show_contacts: false,
  education: [] as PlaceForm[], experience: [] as PlaceForm[], awards: [] as AwardForm[] })

async function load() {
  p.value = null
  failed.value = false
  editing.value = false
  try {
    p.value = await profileApi.get(id.value)
  } catch {
    failed.value = true
  }
}
watch(id, load, { immediate: true })

const subtitle = computed(() => {
  const x = p.value
  if (!x) return ''
  const role = x.position || x.roles.map((r) => (te(`roles.${r}`) ? t(`roles.${r}`) : r)).join(', ')
  return [role, x.branches.join(', ')].filter(Boolean).join(' · ')
})
const empty = computed(() => {
  const x = p.value
  return !!x && !x.about && !x.education.length && !x.experience.length && !x.awards.length
})
const years = (x: { year_from: number | null; year_to: number | null }) =>
  x.year_from || x.year_to ? `${x.year_from ?? '…'} – ${x.year_to ?? t('nv.profile.now')}` : ''

const placeForm = (x: ProfilePlace): PlaceForm =>
  ({ place: x.place, role: x.role ?? '', year_from: x.year_from ? String(x.year_from) : '', year_to: x.year_to ? String(x.year_to) : '' })
const blankPlace = (): PlaceForm => ({ place: '', role: '', year_from: '', year_to: '' })

function startEdit() {
  const x = p.value
  if (!x) return
  form.value = {
    photo_key: x.photo_key, photo_url: x.photo_url, email: x.email ?? '', about: x.about ?? '', show_contacts: x.show_contacts,
    education: x.education.map(placeForm), experience: x.experience.map(placeForm),
    awards: x.awards.map((a: ProfileAward) => ({ title: a.title, year: a.year ? String(a.year) : '', file_key: a.file_key, file_name: a.file_name })),
  }
  editing.value = true
}

async function pickFile(e: Event, done: (key: string, url: string, name: string) => void) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  busy.value = true
  try {
    const up = await chatsApi.upload(file)
    done(up.key, up.url, up.name)
  } finally {
    busy.value = false
  }
}
const onPhoto = (e: Event) => pickFile(e, (key, url) => { form.value.photo_key = key; form.value.photo_url = url })
const onAwardFile = (e: Event, a: AwardForm) => pickFile(e, (key, _url, name) => { a.file_key = key; a.file_name = name })

const year = (s: string) => (s && Number(s) ? Number(s) : null)
const toPlace = (x: PlaceForm): ProfilePlace => ({ place: x.place.trim(), role: x.role.trim() || null, year_from: year(x.year_from), year_to: year(x.year_to) })

async function save() {
  const f = form.value
  saving.value = true
  try {
    p.value = await profileApi.save(id.value, {
      photo_key: f.photo_key, email: f.email.trim() || null, about: f.about.trim() || null, show_contacts: f.show_contacts,
      education: f.education.filter((x) => x.place.trim()).map(toPlace),
      experience: f.experience.filter((x) => x.place.trim()).map(toPlace),
      awards: f.awards.filter((a) => a.title.trim()).map((a) => ({ title: a.title.trim(), year: year(a.year), file_key: a.file_key, file_name: a.file_name })),
    })
    editing.value = false
    toast.ok(t('nv.profile.saved'))
    if (id.value === auth.user?.id) await auth.fetchMe()
  } finally {
    saving.value = false
  }
}

async function copyLink() {
  const url = `${location.origin}/staff/${id.value}`
  try {
    await navigator.clipboard.writeText(url)
    toast.ok(t('nv.profile.copied'))
  } catch {
    window.prompt(t('nv.profile.link'), url)
  }
}
</script>

<template>
  <div class="prof">
    <UiSkeleton v-if="!p && !failed" :lines="6" />
    <UiEmptyState v-else-if="!p" icon="users" :title="t('nv.profile.notFound')" />

    <template v-else-if="!editing">
      <UiCard>
        <div class="prof-head">
          <img v-if="p.photo_url" :src="p.photo_url" :alt="p.full_name" class="prof-photo" />
          <div v-else class="prof-photo ph"><UiIcon name="user" :size="40" /></div>
          <div class="grow">
            <h1 class="prof-name">{{ p.full_name }}</h1>
            <div class="muted">{{ subtitle }}</div>
            <div v-if="p.phone || p.email" class="prof-contacts">
              <a v-if="p.phone" :href="`tel:+${p.phone}`">{{ formatPhone(p.phone) }}</a>
              <a v-if="p.email" :href="`mailto:${p.email}`">{{ p.email }}</a>
            </div>
            <div class="head-acts" style="margin-top: 12px">
              <UiButton v-if="p.can_edit" variant="primary" icon="edit" @click="startEdit">{{ t('nv.profile.fill') }}</UiButton>
              <UiButton icon="send" @click="copyLink">{{ t('nv.profile.copy') }}</UiButton>
            </div>
          </div>
        </div>
      </UiCard>

      <UiCard v-if="empty" style="margin-top: 14px"><p class="muted m0">{{ t('nv.profile.empty') }}</p></UiCard>
      <UiCard v-if="p.about" :title="t('nv.profile.about')" style="margin-top: 14px"><p class="m0 pre">{{ p.about }}</p></UiCard>
      <UiCard v-if="p.education.length" :title="t('nv.profile.education')" style="margin-top: 14px">
        <div v-for="(x, i) in p.education" :key="i" class="list-row">
          <div class="grow"><b>{{ x.place }}</b><span>{{ [x.role, years(x)].filter(Boolean).join(' · ') }}</span></div>
        </div>
      </UiCard>
      <UiCard v-if="p.experience.length" :title="t('nv.profile.experience')" style="margin-top: 14px">
        <div v-for="(x, i) in p.experience" :key="i" class="list-row">
          <div class="grow"><b>{{ x.place }}</b><span>{{ [x.role, years(x)].filter(Boolean).join(' · ') }}</span></div>
        </div>
      </UiCard>
      <UiCard v-if="p.awards.length" :title="t('nv.profile.awards')" style="margin-top: 14px">
        <div v-for="(a, i) in p.awards" :key="i" class="list-row">
          <div class="grow"><b>{{ a.title }}</b><span v-if="a.year">{{ a.year }}</span></div>
          <a v-if="a.file_url" :href="a.file_url" target="_blank" rel="noopener" class="btn sm"><UiIcon name="file" :size="16" />{{ t('nv.profile.open') }}</a>
        </div>
      </UiCard>
    </template>

    <template v-else>
      <UiCard :title="t('nv.profile.editTitle', { name: p.full_name })">
        <div class="prof-head">
          <img v-if="form.photo_url" :src="form.photo_url" alt="" class="prof-photo" />
          <div v-else class="prof-photo ph"><UiIcon name="user" :size="40" /></div>
          <div class="grow">
            <div class="head-acts">
              <label class="btn" :class="{ disabled: busy }"><UiIcon name="camera" :size="16" />{{ t('nv.profile.photo') }}
                <input type="file" accept="image/jpeg,image/png,image/webp" hidden :disabled="busy" @change="onPhoto" /></label>
              <UiButton v-if="form.photo_key" variant="ghost" @click="form.photo_key = null; form.photo_url = null">{{ t('nv.profile.noPhoto') }}</UiButton>
            </div>
            <div class="muted" style="margin-top: 10px">{{ t('nv.profile.phone') }}: {{ p.phone ? formatPhone(p.phone) : '—' }}</div>
          </div>
        </div>
        <div class="prof-grid" style="margin-top: 14px">
          <UiInput v-model="form.email" type="email" :label="t('nv.profile.email')" :maxlength="120" />
          <div class="set-row"><div class="grow"><b>{{ t('nv.profile.showContacts') }}</b></div><UiSwitch v-model="form.show_contacts" :label="t('nv.profile.showContacts')" /></div>
        </div>
        <UiTextarea v-model="form.about" :label="t('nv.profile.about')" :rows="4" :maxlength="3000" style="margin-top: 12px" />
      </UiCard>

      <UiCard v-for="sec in (['education', 'experience'] as const)" :key="sec" :title="t(`nv.profile.${sec}`)" style="margin-top: 14px">
        <div v-for="(x, i) in form[sec]" :key="i" class="prof-row">
          <UiInput v-model="x.place" :label="t(`nv.profile.${sec}Place`)" :maxlength="200" />
          <UiInput v-model="x.role" :label="t(`nv.profile.${sec}Role`)" :maxlength="200" />
          <UiInput v-model="x.year_from" :label="t('nv.profile.from')" inputmode="numeric" :maxlength="4" placeholder="2018" />
          <UiInput v-model="x.year_to" :label="t('nv.profile.to')" inputmode="numeric" :maxlength="4" :placeholder="t('nv.profile.now')" />
          <UiButton variant="ghost" icon="delete" :aria-label="t('common.remove')" :title="t('common.remove')" @click="form[sec].splice(i, 1)" />
        </div>
        <UiButton icon="plus" @click="form[sec].push(blankPlace())">{{ t('nv.profile.add') }}</UiButton>
      </UiCard>

      <UiCard :title="t('nv.profile.awards')" style="margin-top: 14px">
        <div v-for="(a, i) in form.awards" :key="i" class="prof-row aw">
          <UiInput v-model="a.title" :label="t('nv.profile.awardTitle')" :maxlength="200" />
          <UiInput v-model="a.year" :label="t('nv.profile.year')" inputmode="numeric" :maxlength="4" />
          <label class="btn" :class="{ disabled: busy }"><UiIcon name="clip" :size="16" /><span class="fname">{{ a.file_name || t('nv.profile.file') }}</span>
            <input type="file" accept="image/*,application/pdf" hidden :disabled="busy" @change="onAwardFile($event, a)" /></label>
          <UiButton variant="ghost" icon="delete" :aria-label="t('common.remove')" :title="t('common.remove')" @click="form.awards.splice(i, 1)" />
        </div>
        <UiButton icon="plus" @click="form.awards.push({ title: '', year: '', file_key: null, file_name: null })">{{ t('nv.profile.add') }}</UiButton>
      </UiCard>

      <div class="head-acts" style="margin-top: 16px">
        <UiButton variant="primary" :loading="saving" :disabled="busy" @click="save">{{ t('common.save') }}</UiButton>
        <UiButton :disabled="saving" @click="editing = false">{{ t('common.cancel') }}</UiButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.prof { max-width: 860px }
.prof-head { display: flex; gap: 18px; align-items: flex-start; flex-wrap: wrap }
.prof-photo { width: 128px; height: 128px; border-radius: 20px; object-fit: cover; flex: none; border: 1px solid var(--line) }
.prof-photo.ph { display: grid; place-items: center; background: var(--navy-50); color: var(--muted) }
.prof-name { margin: 0 0 4px; font-family: var(--font-display); font-size: 22px }
.prof-contacts { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 8px; font-weight: 600 }
.prof-contacts a { color: var(--accent-ink); text-decoration: none }
.prof-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; align-items: end }
.prof-row { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 2fr) 84px 84px auto; gap: 8px; align-items: end; margin-bottom: 12px }
.prof-row.aw { grid-template-columns: minmax(0, 3fr) 84px minmax(0, 2fr) auto }
.fname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 180px }
.pre { white-space: pre-wrap }
.btn.disabled { opacity: .6; pointer-events: none }
@media (max-width: 720px) {
  .prof-grid { grid-template-columns: minmax(0, 1fr) }
  .prof-row, .prof-row.aw { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); padding-bottom: 12px; border-bottom: 1px solid var(--line) }
  .prof-row > :first-child { grid-column: 1 / -1 }
  .prof-photo { width: 96px; height: 96px }
}
</style>
