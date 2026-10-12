<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-1 gap-3">
      <h1 class="text-2xl font-bold">Releases</h1>
      <select v-model="project" @change="reload" class="ctl">
        <option :value="null">All projects</option>
        <option v-for="p in projects" :key="p.name" :value="p.name">{{ p.project_name || p.name }}</option>
      </select>
    </div>
    <p class="text-xs text-faint mb-4">Tag a task with a release (e.g. <b>v1.2</b>) in its detail panel — they group here automatically.</p>

    <div v-if="loading" class="space-y-2">
      <div v-for="n in 3" :key="n" class="card-surface p-4"><Skeleton width="35%" height="14px" /></div>
    </div>

    <div v-else class="space-y-2.5">
      <div v-for="r in releases" :key="r.release_name" class="card-surface">
        <div class="p-4 cursor-pointer" @click="toggle(r)">
          <div class="flex items-center gap-3">
            <ChevronRight class="w-4 h-4 text-faint transition-transform shrink-0" :class="{ 'rotate-90': open === r.release_name }" />
            <Tag class="w-3.5 h-3.5 shrink-0" style="color:var(--accent)" />
            <span class="font-medium text-app truncate flex-1">{{ r.release_name }}</span>
            <span class="text-xs text-muted tnum shrink-0">{{ r.done }}/{{ r.total }} done</span>
            <span class="text-xs tnum w-10 text-right" :style="{ color: r.pct === 100 ? 'var(--term-green)' : 'var(--muted)' }">{{ r.pct }}%</span>
          </div>
          <div class="h-1 bg-surface-2 mt-2.5 overflow-hidden">
            <div class="h-full" :style="{ width: r.pct + '%', background: r.pct === 100 ? 'var(--term-green)' : 'var(--accent)' }" />
          </div>
        </div>

        <div v-if="open === r.release_name" class="border-t border-soft px-4 py-2">
          <div v-for="t in tasks" :key="t.name" @click="openId = t.name"
            class="flex items-center gap-3 py-1.5 cursor-pointer hover-app">
            <span class="mono text-[10px] text-faint w-16 shrink-0">{{ t.issue_key }}</span>
            <span class="flex-1 truncate text-sm" :class="t.status === 'Completed' ? 'line-through text-muted' : ''">{{ t.subject }}</span>
            <StatusPill :value="t.status" />
          </div>
          <div v-if="!tasks.length" class="text-xs text-faint py-3 text-center">No tasks in this release.</div>
        </div>
      </div>
      <div v-if="!releases.length" class="py-16 text-center text-faint">No releases yet. Set a release on a task to start grouping.</div>
    </div>

    <TaskDrawer :task-id="openId" @close="openId = null" @changed="reload" @open="openId = $event" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { call } from 'frappe-ui'
import TaskDrawer from '@/components/TaskDrawer.vue'
import StatusPill from '@/ui/StatusPill.vue'
import Skeleton from '@/ui/Skeleton.vue'
import ChevronRight from '~icons/lucide/chevron-right'
import Tag from '~icons/lucide/tag'

const loading = ref(true)
const releases = ref([])
const projects = ref([])
const project = ref(null)
const open = ref(null)
const tasks = ref([])
const openId = ref(null)

async function toggle(r) {
  if (open.value === r.release_name) { open.value = null; return }
  open.value = r.release_name
  tasks.value = await call('pulse.api.planning.release_tasks', { release: r.release_name, project: project.value }).catch(() => [])
}

async function reload() {
  loading.value = true
  releases.value = await call('pulse.api.planning.list_releases', { project: project.value }).catch(() => [])
  if (open.value) {
    tasks.value = await call('pulse.api.planning.release_tasks', { release: open.value, project: project.value }).catch(() => [])
  }
  loading.value = false
}

onMounted(async () => {
  projects.value = await call('pulse.api.spa.get_projects').catch(() => [])
  reload()
})
</script>

<style scoped>
.ctl { background: var(--surface); border: 1px solid var(--border); color: var(--text); font-size: 12px; border-radius: 9px; padding: 7px 10px; outline: none; }
</style>
