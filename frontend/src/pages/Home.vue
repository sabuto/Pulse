<template>
  <div class="p-6 max-w-5xl mx-auto">
    <div class="text-center mt-6 mb-8">
      <h1 class="text-2xl font-bold">{{ greeting }}, {{ firstName }}</h1>
      <p class="text-sm text-muted mt-1">{{ dateStr }}</p>
    </div>

    <!-- KPI row -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
      <div v-for="k in kpis" :key="k.label" class="card-surface p-4">
        <div class="text-xs text-muted">{{ k.label }}</div>
        <div class="text-2xl font-bold mt-1">{{ k.value }}</div>
      </div>
    </div>

    <div class="flex items-center justify-between mb-2">
      <h2 class="text-sm font-semibold">Recents</h2>
      <router-link to="/board" class="text-xs text-accent">Open board</router-link>
    </div>
    <div class="card-surface divide-y divide-app">
      <div v-for="t in recents" :key="t.name" @click="openId = t.name"
        class="flex items-center gap-3 px-4 py-3 hover-app cursor-pointer">
        <span class="text-[11px] font-mono text-muted w-16 shrink-0">{{ t.issue_key }}</span>
        <span class="flex-1 truncate">{{ t.subject }}</span>
        <span class="text-[10px] px-1.5 py-0.5 rounded bg-surface-2 text-muted">{{ t.status }}</span>
        <span class="text-[10px] text-muted">{{ fromNow(t.modified) }}</span>
      </div>
      <div v-if="!recents.length" class="px-4 py-10 text-center text-muted text-sm">No recent items.</div>
    </div>

    <TaskDrawer :task-id="openId" @close="openId = null" @changed="reload" @open="openId = $event" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { call } from 'frappe-ui'
import TaskDrawer from '@/components/TaskDrawer.vue'

const firstName = ref('there')
const stats = ref({})
const recents = ref([])
const openId = ref(null)

const now = new Date()
const greeting = computed(() => {
  const h = now.getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
})
const dateStr = now.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })

const kpis = computed(() => [
  { label: 'My open tasks', value: stats.value.my_tasks ?? 0 },
  { label: 'Overdue', value: stats.value.overdue ?? 0 },
  { label: 'Active projects', value: stats.value.active_projects ?? 0 },
  { label: 'Total open', value: stats.value.total_open ?? 0 },
])

function fromNow(dt) {
  if (!dt) return ''
  const diff = (Date.now() - new Date(dt.replace(' ', 'T')).getTime()) / 1000
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}

async function reload() {
  const [u, s, r] = await Promise.all([
    call('frappe.auth.get_logged_user'),
    call('pulse.api.dashboards.get_dashboard_stats').catch(() => ({})),
    call('pulse.api.spa.list_tasks', { which: 'recent', limit: 8 }).catch(() => []),
  ])
  const full = await call('frappe.client.get_value', { doctype: 'User', filters: u, fieldname: 'first_name' }).catch(() => null)
  firstName.value = (full && full.first_name) || (u || '').split('@')[0]
  stats.value = s
  recents.value = r
}
onMounted(reload)
</script>
