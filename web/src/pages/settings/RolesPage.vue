<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiChip, UiEmptyState, UiInput, UiPrompt, UiSkeleton } from '@/components/ui'
import { adminApi, type PermissionCatalog, type Role } from '@/api/admin'
import type { Scope } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { apiErr } from '@/utils/err'

/** Role builder: module × action × scope. Nobody can grant more than they hold; the server enforces it again. */
const SCOPES: Scope[] = ['own', 'branch', 'network']
const RANK: Record<Scope, number> = { own: 0, branch: 1, network: 2 }
const { t, te } = useI18n()
const auth = useAuthStore()
const toast = useToastStore()
const catalog = ref<PermissionCatalog | null>(null)
const roles = ref<Role[] | null>(null)
const selected = ref<number | 'new' | null>(null)
const form = reactive({ name: '', description: '', coin_limit: '0', grants: {} as Record<string, Scope | ''> })
const error = ref<string | null>(null)
const busy = ref(false)
const archiving = ref(false)
const isOwner = computed(() => !!auth.user?.roles.includes('owner'))
const canManage = computed(() => auth.can('roles.manage'))
const role = computed(() => (typeof selected.value === 'number' ? roles.value?.find((r) => r.id === selected.value) ?? null : null))

/** Why the selected role is read-only for me, or null when I may edit it */
const lockReason = computed(() => {
  if (!canManage.value) return t('rolesPage.lock.noManage')
  const r = role.value
  if (!r) return null
  if (r.code === 'owner') return t('rolesPage.lock.owner')
  if (r.is_system && !isOwner.value) return t('rolesPage.lock.system')
  if (!isOwner.value && auth.user?.roles.includes(r.code)) return t('rolesPage.lock.own')
  return null
})
const readOnly = computed(() => lockReason.value !== null)
const roleLabel = (r: Role) => (r.is_system && te(`roles.${r.code}`) ? t(`roles.${r.code}`) : r.name)
const myScope = (key: string): Scope | null => (isOwner.value ? 'network' : auth.user?.permissions[key] ?? null)
const options = (key: string) => SCOPES.filter((s) => {
  const mine = myScope(key)
  return mine !== null && RANK[s] <= RANK[mine]
})
const granted = computed(() => Object.values(form.grants).filter(Boolean).length)

onMounted(async () => {
  const [c, r] = await Promise.all([adminApi.catalog().catch(() => ({})), adminApi.roles().catch(() => [])])
  catalog.value = c
  roles.value = r
  const first = r.find((x) => !x.archived_at)
  if (first) pick(first.id)
})

function fill(r: Role | null) {
  form.name = r ? roleLabel(r) : ''
  form.description = r?.description ?? ''
  form.coin_limit = String(r?.coin_limit ?? 0)
  form.grants = Object.fromEntries((r?.permissions ?? []).map((p) => [`${p.module}.${p.action}`, p.scope]))
  error.value = null
}
function pick(id: number | 'new') {
  selected.value = id
  fill(id === 'new' ? null : roles.value?.find((r) => r.id === id) ?? null)
}
function setAll(module: string, scope: Scope | '') {
  for (const a of Object.keys(catalog.value?.[module]?.actions ?? {})) {
    const k = `${module}.${a}`
    if (!scope) form.grants[k] = ''
    else if (options(k).includes(scope)) form.grants[k] = scope
    else if (options(k).length) form.grants[k] = options(k)[options(k).length - 1]!
  }
}

async function save() {
  error.value = form.name.trim().length < 2 ? t('rolesPage.nameRequired') : null
  if (error.value) return
  const permissions = Object.entries(form.grants).filter(([, s]) => s).map(([k, s]) => {
    const [module, action] = k.split('.') as [string, string]
    return { module, action, scope: s as Scope }
  })
  const body = { name: form.name.trim(), description: form.description.trim() || null, coin_limit: Math.max(0, Math.round(Number(form.coin_limit) || 0)), permissions }
  busy.value = true
  try {
    const out = selected.value === 'new' ? await adminApi.createRole(body) : await adminApi.updateRole(role.value!.id, body)
    roles.value = selected.value === 'new' ? [...(roles.value ?? []), { ...out, members: 0 }] : roles.value?.map((r) => (r.id === out.id ? { ...out, members: r.members } : r)) ?? null
    selected.value = out.id
    toast.ok(t('common.saved'))
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}
async function archive() {
  const r = role.value
  if (!r) return
  busy.value = true
  try {
    await adminApi.archiveRole(r.id)
    roles.value = roles.value?.filter((x) => x.id !== r.id) ?? null
    archiving.value = false
    toast.ok(t('rolesPage.archived'))
    const first = roles.value?.[0]
    if (first) pick(first.id)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('nav.roles') }}</h1><p>{{ t('rolesPage.subtitle') }}</p></div>
    <span class="sp" />
    <UiButton v-if="canManage" variant="primary" icon="plus" @click="pick('new')">{{ t('rolesPage.new') }}</UiButton>
  </div>

  <div v-if="!roles || !catalog" class="grid roles-grid"><div class="card card-pad"><UiSkeleton :lines="6" /></div><div class="card card-pad"><UiSkeleton :lines="10" /></div></div>
  <div v-else class="grid roles-grid">
    <UiCard flush>
      <div class="role-list" role="listbox" :aria-label="t('nav.roles')">
        <button v-for="r in roles.filter((x) => !x.archived_at)" :key="r.id" type="button" role="option" class="list-row" :aria-selected="selected === r.id" :class="{ sel: selected === r.id }" @click="pick(r.id)">
          <div class="grow"><b>{{ roleLabel(r) }}</b><span>{{ t('rolesPage.members', { n: r.members }) }} · {{ t('rolesPage.perms', { n: r.permissions.length }) }}</span></div>
          <UiChip v-if="r.is_system" small>{{ t('rolesPage.system') }}</UiChip>
        </button>
        <button v-if="selected === 'new'" type="button" class="list-row sel" aria-selected="true"><div class="grow"><b>{{ form.name || t('rolesPage.newTitle') }}</b><span>{{ t('rolesPage.draft') }}</span></div></button>
      </div>
    </UiCard>

    <UiCard v-if="selected !== null">
      <form class="stack" @submit.prevent="save">
        <div v-if="lockReason" class="alert info m0"><span>{{ lockReason }}</span></div>
        <div class="form-2">
          <UiInput v-model="form.name" :label="t('rolesPage.name')" :maxlength="120" :disabled="readOnly" />
          <UiInput v-model="form.coin_limit" type="number" :min="0" :label="t('rolesPage.coinLimit')" :hint="t('rolesPage.coinHint')" :disabled="readOnly" inputmode="numeric" />
        </div>
        <UiInput v-model="form.description" :label="t('rolesPage.description')" :maxlength="255" :disabled="readOnly" />
        <div class="perm-head"><b>{{ t('rolesPage.matrix') }}</b><span class="muted">{{ t('rolesPage.granted', { n: granted }) }}</span></div>
        <p class="form-note">{{ t('rolesPage.scopeNote') }}</p>
        <div class="perm-mods">
          <section v-for="(m, mk) in catalog" :key="mk" class="perm-mod">
            <header>
              <b>{{ te(`rolesPage.mod.${mk}`) ? t(`rolesPage.mod.${mk}`) : m.title }}</b>
              <span v-if="!readOnly" class="perm-all">
                <button type="button" class="linkbtn" @click="setAll(String(mk), 'branch')">{{ t('rolesPage.allBranch') }}</button>
                <button type="button" class="linkbtn" @click="setAll(String(mk), '')">{{ t('rolesPage.none') }}</button>
              </span>
            </header>
            <div class="perm-acts">
              <label v-for="(title, ak) in m.actions" :key="ak" class="perm-act" :class="{ on: !!form.grants[`${mk}.${ak}`] }">
                <span>{{ te(`rolesPage.act.${mk}.${ak}`) ? t(`rolesPage.act.${mk}.${ak}`) : title }}</span>
                <select v-model="form.grants[`${mk}.${ak}`]" class="inp perm-sel" :disabled="readOnly || (!options(`${mk}.${ak}`).length && !form.grants[`${mk}.${ak}`])" :aria-label="`${m.title}: ${title}`">
                  <option value="">—</option>
                  <option v-for="s in SCOPES" :key="s" :value="s" :disabled="!options(`${mk}.${ak}`).includes(s)">{{ t(`rolesPage.scope.${s}`) }}</option>
                </select>
              </label>
            </div>
          </section>
        </div>
        <p v-if="error" class="form-err" role="alert">{{ error }}</p>
        <div v-if="!readOnly" class="row-acts" style="justify-content: flex-start">
          <UiButton type="submit" variant="navy" :loading="busy">{{ selected === 'new' ? t('rolesPage.create') : t('common.save') }}</UiButton>
          <UiButton v-if="role && !role.is_system" variant="ghost" icon="archive" @click="archiving = true">{{ t('rolesPage.archive') }}</UiButton>
        </div>
      </form>
    </UiCard>
    <UiEmptyState v-else icon="key" :title="t('rolesPage.pick')" />
  </div>

  <UiPrompt :open="archiving" :title="t('rolesPage.archiveTitle')" :text="role ? t('rolesPage.archiveText', { name: roleLabel(role), n: role.members }) : ''" :confirm-label="t('rolesPage.archive')" danger :busy="busy" @update:open="(v) => (archiving = v)" @confirm="archive" />
</template>
