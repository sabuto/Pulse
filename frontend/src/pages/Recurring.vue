<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-1">
      <h1 class="text-2xl font-bold">Recurring Tasks</h1>
      <button v-if="canWrite" @click="openCreate({ repeat: true })" class="btn-primary">
        <Plus class="w-3.5 h-3.5" /> New recurring task
      </button>
    </div>
    <p class="text-xs text-faint mb-4">Routine work that regenerates on a schedule — a fresh task lands in <b>To Do</b> each cycle, so it never rots in the backlog.</p>

    <div v-if="loading" class="space-y-2">
      <div v-for="n in 3" :key="n" class="card-surface p-4"><Skeleton width="40%" height="14px" /></div>
    </div>

    <div v-else class="space-y-2.5">
      <div v-for="r in rows" :key="r.name" class="card-surface p-4" :class="{ 'opacity-60': !r.is_active }">
        <div class="flex items-center justify-between gap-3">
          <div class="min-w-0">
            <div class="font-medium text-app truncate">{{ r.subject }}</div>
            <div class="flex items-center gap-4 mt-1.5 text-xs text-muted flex-wrap">
              <span class="tele text-accent">{{ r.cadence }}</span>
              <span>{{ r.project }}</span>
              <span class="inline-flex items-center gap-1.5"><CalendarDays class="w-3.5 h-3.5" />next: {{ r.next_run || '—' }}</span>
              <span v-if="r.last_generated" class="text-faint">last: {{ r.last_generated }}</span>
              <span v-if="!r.is_active" class="tele text-[10px] text-faint">paused</span>
            </div>
          </div>
          <div v-if="canWrite" class="flex items-center gap-1.5 shrink-0">
            <button class="icon-btn" title="Generate a task now" @click="runNow(r)"><Play class="w-4 h-4" /></button>
            <button class="icon-btn" :title="r.is_active ? 'Pause' : 'Resume'" @click="toggle(r)">
              <Pause v-if="r.is_active" class="w-4 h-4" />
              <RotateCw v-else class="w-4 h-4" />
            </button>
            <button class="icon-btn danger" title="Delete" @click="remove(r)"><Trash2 class="w-4 h-4" /></button>
          </div>
        </div>
      </div>
      <div v-if="!rows.length" class="py-16 text-center text-faint">No recurring tasks yet. Create one so routine work never rots in the backlog.</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { canWrite } from '@/utils/access'
import { call } from 'frappe-ui'
import Skeleton from '@/ui/Skeleton.vue'
import { openCreate, createState } from '@/ui/create'
import { toast } from '@/ui/toast'
import Plus from '~icons/lucide/plus'
import Play from '~icons/lucide/play'
import Pause from '~icons/lucide/pause'
import RotateCw from '~icons/lucide/rotate-cw'
import Trash2 from '~icons/lucide/trash-2'
import CalendarDays from '~icons/lucide/calendar-days'

const loading = ref(true)
const rows = ref([])

async function reload() {
  loading.value = true
  rows.value = await call('pulse.api.recurring.list_recurring').catch(() => [])
  loading.value = false
}
async function toggle(r) {
  await call('pulse.api.recurring.toggle_recurring', { name: r.name, is_active: r.is_active ? 0 : 1 }).catch(() => {})
  reload()
}
async function runNow(r) {
  try { await call('pulse.api.recurring.generate_now', { name: r.name }); toast.success('Task generated in To Do'); reload() }
  catch (e) { toast.error('Could not generate task') }
}
async function remove(r) {
  if (!confirm(`Delete recurring "${r.subject}"? Tasks already generated are kept.`)) return
  await call('pulse.api.recurring.delete_recurring', { name: r.name }).catch(() => {})
  reload()
}
watch(() => createState.created, reload)
onMounted(reload)
</script>

<style scoped>
.new-btn { background: var(--accent); transition: filter 0.12s; }
.new-btn:hover { filter: brightness(1.08); }
.icon-btn { padding: 6px; border-radius: 9px; border: 1px solid var(--border); color: var(--muted); background: transparent; }
.icon-btn:hover { color: var(--text); border-color: var(--accent); }
.icon-btn.danger:hover { color: var(--danger); border-color: var(--danger); }
</style>
