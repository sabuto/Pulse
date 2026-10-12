<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h1 class="text-2xl font-bold">Audit Logs</h1>
        <p class="text-sm text-muted">Timestamped monitor log of activity across Pulse.</p>
      </div>
      <select v-model="project" @change="load" class="text-xs bg-surface border border-app rounded-md px-2 py-1.5">
        <option :value="null">All projects</option>
        <option v-for="p in projects" :key="p.name" :value="p.name">{{ p.project_name || p.name }}</option>
      </select>
    </div>

    <div v-if="loading" class="text-muted py-20 text-center">Loading...</div>
    <div v-else class="card-surface overflow-x-auto">
      <table class="data-table">
        <thead>
          <tr>
            <th class="w-44">Timestamp</th>
            <th>User</th>
            <th>Action</th>
            <th>Reference</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(e, i) in entries" :key="i">
            <td class="text-muted mono text-xs">{{ fmt(e.timestamp) }}</td>
            <td>
              <span class="inline-flex items-center gap-2">
                <span class="w-6 h-6 rounded-full text-[9px] grid place-items-center font-bold" style="background:var(--accent);color:var(--on-accent)">{{ initials(e.user) }}</span>
                {{ (e.user || '').split('@')[0] }}
              </span>
            </td>
            <td><span class="text-[10px] px-2 py-0.5 rounded-full" :class="actionClass(e.action)">{{ e.action }}</span></td>
            <td class="mono text-xs text-muted">{{ e.reference || '-' }}</td>
            <td class="text-muted truncate max-w-xs">{{ e.detail || '-' }}</td>
          </tr>
          <tr v-if="!entries.length"><td colspan="5" class="py-10 text-center text-muted">No audit entries.</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { call } from 'frappe-ui'

const loading = ref(true)
const entries = ref([])
const projects = ref([])
const project = ref(null)

function initials(e) { return (e || '?').replace(/@.*/, '').slice(0, 2).toUpperCase() }
function fmt(ts) { return ts ? ts.replace('T', ' ').slice(0, 19) : '' }
function actionClass(act) {
  // readable in BOTH themes: dark ink on light, bright ink on dark
  const base = 'border font-medium'
  if (/status/i.test(act)) return `${base} bg-amber-500/15 border-amber-500/40 text-amber-800 dark:text-amber-300`
  if (/assign/i.test(act)) return `${base} bg-sky-500/15 border-sky-500/40 text-sky-800 dark:text-sky-300`
  if (/comment/i.test(act)) return `${base} bg-emerald-500/15 border-emerald-500/40 text-emerald-800 dark:text-emerald-300`
  if (/creat/i.test(act)) return `${base} bg-violet-500/15 border-violet-500/40 text-violet-800 dark:text-violet-300`
  return `${base} bg-gray-500/15 border-gray-500/40 text-gray-800 dark:text-gray-300`
}

async function load() {
  loading.value = true
  const [e, ps] = await Promise.all([
    call('pulse.api.audit.get_audit_log', { project: project.value, limit: 200 }),
    projects.value.length ? Promise.resolve(projects.value)
      : call('pulse.api.spa.get_projects'),
  ])
  entries.value = e || []
  projects.value = ps
  loading.value = false
}
onMounted(load)
</script>
