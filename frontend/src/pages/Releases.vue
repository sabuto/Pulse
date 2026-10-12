<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-1 gap-3">
      <h1 class="text-2xl font-bold">Releases</h1>
      <div class="flex items-center gap-2">
        <select v-model="appFilter" @change="reload" class="ctl">
          <option :value="null">All apps</option>
          <option v-for="a in apps" :key="a" :value="a">{{ a }}</option>
          <option value="none">No app</option>
        </select>
        <select v-model="project" @change="reload" class="ctl">
          <option :value="null">All projects</option>
          <option v-for="p in projects" :key="p.name" :value="p.name">{{ p.project_name || p.name }}</option>
        </select>
      </div>
    </div>
    <p class="text-xs text-faint mb-4">Tag a task with an app and a release (e.g. <b>v1.2</b>) in its detail panel — they group here by app automatically.</p>

    <div v-if="loading" class="space-y-2">
      <div v-for="n in 3" :key="n" class="card-surface p-4"><Skeleton width="35%" height="14px" /></div>
    </div>

    <div v-else class="space-y-5">
      <section v-for="g in groups" :key="g.app || 'none'">
        <div class="flex items-center gap-2 mb-2">
          <Package class="w-4 h-4 shrink-0" style="color:var(--accent)" />
          <h2 class="text-sm font-semibold text-app">{{ g.app || 'No app' }}</h2>
          <span class="text-xs text-faint">{{ g.releases.length }} release{{ g.releases.length === 1 ? '' : 's' }}</span>
        </div>
        <div class="space-y-2.5">
          <div v-for="r in g.releases" :key="keyOf(r)" class="card-surface">
            <div class="p-4 cursor-pointer" @click="toggle(r)">
              <div class="flex items-center gap-3">
                <ChevronRight class="w-4 h-4 text-faint transition-transform shrink-0" :class="{ 'rotate-90': open === keyOf(r) }" />
                <Tag class="w-3.5 h-3.5 shrink-0" style="color:var(--accent)" />
                <span class="font-medium text-app truncate flex-1">{{ r.release_name }}</span>
                <span class="text-xs text-muted tnum shrink-0">{{ r.done }}/{{ r.total }} done</span>
                <span class="text-xs tnum w-10 text-right" :style="{ color: r.pct === 100 ? 'var(--term-green)' : 'var(--muted)' }">{{ r.pct }}%</span>
              </div>
              <div class="h-1 bg-surface-2 mt-2.5 overflow-hidden">
                <div class="h-full" :style="{ width: r.pct + '%', background: r.pct === 100 ? 'var(--term-green)' : 'var(--accent)' }" />
              </div>
            </div>

            <div v-if="open === keyOf(r)" class="border-t border-soft px-4 py-2">
              <div v-for="t in tasks" :key="t.name" @click="openId = t.name"
                class="flex items-center gap-3 py-1.5 cursor-pointer hover-app">
                <span class="mono text-[10px] text-faint w-16 shrink-0">{{ t.issue_key }}</span>
                <span class="flex-1 truncate text-sm" :class="t.status === 'Completed' ? 'line-through text-muted' : ''">{{ t.subject }}</span>
                <StatusPill :value="t.status" />
              </div>
              <div v-if="!tasks.length" class="text-xs text-faint py-3 text-center">No tasks in this release.</div>
            </div>
          </div>
        </div>
      </section>
      <div v-if="!groups.length" class="py-16 text-center text-faint">No releases yet. Set a release (and its app) on a task to start grouping.</div>
    </div>

    <TaskDrawer :task-id="openId" @close="openId = null" @changed="reload" @open="openId = $event" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { call } from 'frappe-ui'
import TaskDrawer from '@/components/TaskDrawer.vue'
import StatusPill from '@/ui/StatusPill.vue'
import Skeleton from '@/ui/Skeleton.vue'
import ChevronRight from '~icons/lucide/chevron-right'
import Tag from '~icons/lucide/tag'
import Package from '~icons/lucide/package'

const loading = ref(true)
const releases = ref([])
const projects = ref([])
const project = ref(null)
const apps = ref([])
const appFilter = ref(null)
const open = ref(null)
const tasks = ref([])
const openId = ref(null)

// A release is an app + a tag, so the same tag under two apps is two releases.
const keyOf = (r) => `${r.app || ''}|${r.release_name}`

// One section per configured app (in Pulse Settings order), then anything else
// that's in use (an app since removed from the list), then releases with no app.
const groups = computed(() => {
  const by = new Map()
  for (const r of releases.value) {
    if (!by.has(r.app || '')) by.set(r.app || '', [])
    by.get(r.app || '').push(r)
  }
  const order = [...apps.value, ...[...by.keys()].filter((k) => k && !apps.value.includes(k)), '']
  return order.filter((a) => by.has(a)).map((a) => ({ app: a, releases: by.get(a) }))
})

function taskArgs(r) {
  return { release: r.release_name, project: project.value, app: r.app || 'none' }
}

async function toggle(r) {
  if (open.value === keyOf(r)) { open.value = null; return }
  open.value = keyOf(r)
  tasks.value = await call('pulse.api.planning.release_tasks', taskArgs(r)).catch(() => [])
}

async function reload() {
  loading.value = true
  releases.value = await call('pulse.api.planning.list_releases',
    { project: project.value, app: appFilter.value }).catch(() => [])
  const current = releases.value.find((r) => keyOf(r) === open.value)
  if (current) tasks.value = await call('pulse.api.planning.release_tasks', taskArgs(current)).catch(() => [])
  else open.value = null
  loading.value = false
}

onMounted(async () => {
  projects.value = await call('pulse.api.spa.get_projects').catch(() => [])
  apps.value = await call('pulse.api.spa.get_release_apps').catch(() => [])
  reload()
})
</script>

<style scoped>
.ctl { background: var(--surface); border: 1px solid var(--border); color: var(--text); font-size: 12px; border-radius: 9px; padding: 7px 10px; outline: none; }
</style>
