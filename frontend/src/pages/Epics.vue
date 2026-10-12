<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-1 gap-3">
      <h1 class="text-2xl font-bold">Epics</h1>
      <div class="flex items-center gap-2">
        <select v-model="project" @change="reload" class="ctl">
          <option :value="null">All projects</option>
          <option v-for="p in projects" :key="p.name" :value="p.name">{{ p.project_name || p.name }}</option>
        </select>
        <button v-if="canWrite" @click="openCreate({ project, task_type: 'Epic' })" class="btn-primary">
          <Plus class="w-3.5 h-3.5" /> New epic
        </button>
      </div>
    </div>
    <p class="text-xs text-faint mb-4">An epic is a task of type <b>Epic</b>; link work to it from a task's Epic field. Progress is task count.</p>

    <div v-if="loading" class="space-y-2">
      <div v-for="n in 3" :key="n" class="card-surface p-4"><Skeleton width="40%" height="14px" /></div>
    </div>

    <div v-else class="space-y-2.5">
      <div v-for="e in epics" :key="e.name" class="card-surface">
        <div class="p-4 cursor-pointer" @click="toggle(e)">
          <div class="flex items-center gap-3">
            <ChevronRight class="w-4 h-4 text-faint transition-transform shrink-0" :class="{ 'rotate-90': open === e.name }" />
            <span class="mono text-[11px] text-faint shrink-0">{{ e.issue_key || '—' }}</span>
            <span class="font-medium text-app truncate flex-1">{{ e.subject }}</span>
            <span class="text-xs text-muted tnum shrink-0">{{ e.done }}/{{ e.total }}</span>
            <StatusPill :value="e.status" />
          </div>
          <div class="h-1 bg-surface-2 mt-2.5 overflow-hidden">
            <div class="h-full" :style="{ width: e.pct + '%', background: 'var(--accent)' }" />
          </div>
        </div>

        <div v-if="open === e.name" class="border-t border-soft px-4 py-2">
          <div v-for="t in children" :key="t.name" @click="openId = t.name"
            class="flex items-center gap-3 py-1.5 cursor-pointer hover-app">
            <span class="mono text-[10px] text-faint w-16 shrink-0">{{ t.issue_key }}</span>
            <span class="flex-1 truncate text-sm" :class="t.status === 'Completed' ? 'line-through text-muted' : ''">{{ t.subject }}</span>
            <!-- mono, not .tele: release tags must render exactly as stored (v1.2, not V1.2) -->
            <span v-if="t.pulse_release" class="mono text-[10px] text-accent shrink-0">{{ t.pulse_release }}</span>
            <StatusPill :value="t.status" />
          </div>
          <div v-if="!children.length" class="text-xs text-faint py-3 text-center">No tasks linked to this epic yet.</div>
        </div>
      </div>
      <div v-if="!epics.length" class="py-16 text-center text-faint">No epics yet. Create a task of type <b>Epic</b> to group work.</div>
    </div>

    <TaskDrawer :task-id="openId" @close="openId = null" @changed="reload" @open="openId = $event" />
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { canWrite } from '@/utils/access'
import { call } from 'frappe-ui'
import TaskDrawer from '@/components/TaskDrawer.vue'
import StatusPill from '@/ui/StatusPill.vue'
import Skeleton from '@/ui/Skeleton.vue'
import { openCreate, createState } from '@/ui/create'
import Plus from '~icons/lucide/plus'
import ChevronRight from '~icons/lucide/chevron-right'

const loading = ref(true)
const epics = ref([])
const projects = ref([])
const project = ref(null)
const open = ref(null)
const children = ref([])
const openId = ref(null)

async function toggle(e) {
  if (open.value === e.name) { open.value = null; return }
  open.value = e.name
  children.value = await call('pulse.api.planning.epic_tasks', { epic: e.name }).catch(() => [])
}

async function reload() {
  loading.value = true
  epics.value = await call('pulse.api.planning.list_epics', { project: project.value }).catch(() => [])
  if (open.value) {
    children.value = await call('pulse.api.planning.epic_tasks', { epic: open.value }).catch(() => [])
  }
  loading.value = false
}

watch(() => createState.created, reload)
onMounted(async () => {
  projects.value = await call('pulse.api.spa.get_projects').catch(() => [])
  reload()
})
</script>

<style scoped>
.ctl { background: var(--surface); border: 1px solid var(--border); color: var(--text); font-size: 12px; border-radius: 9px; padding: 7px 10px; outline: none; }
.new-btn { background: var(--accent); transition: filter 0.12s; }
.new-btn:hover { filter: brightness(1.08); }
</style>
