<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-1 gap-3 flex-wrap">
      <h1 class="text-2xl font-bold">Reports</h1>
      <div class="flex items-center gap-2">
        <select v-model="reportKey" @change="load" class="ctl">
          <option v-for="r in reports" :key="r.key" :value="r.key">{{ r.label }}</option>
        </select>
        <select v-model="project" @change="onProject" class="ctl">
          <option :value="null">All projects</option>
          <option v-for="p in projects" :key="p.name" :value="p.name">{{ p.project_name || p.name }}</option>
        </select>
        <select v-if="current?.needs_sprint" v-model="sprint" @change="load" class="ctl">
          <option :value="null">Active sprint</option>
          <option v-for="s in sprints" :key="s.name" :value="s.name">{{ s.sprint_name || s.name }} ({{ s.status }})</option>
        </select>
      </div>
    </div>
    <p class="text-xs text-faint mb-4">Measured in task count — Pulse doesn't use story points.</p>

    <div v-if="loading" class="py-20 text-center text-muted">Loading report…</div>
    <div v-else-if="error" class="py-16 text-center text-faint">{{ error }}</div>
    <div v-else-if="!rows.length" class="py-16 text-center text-faint">
      No data for this report yet. Sprint reports need a sprint with dates and tasks.
    </div>

    <div v-else>
      <!-- line chart for burndown / burnup -->
      <div v-if="chart && points.length > 1" class="card-surface p-4 mb-4">
        <svg :viewBox="`0 0 ${W} ${H}`" class="w-full" style="height:220px">
          <line :x1="pad" :y1="H - pad" :x2="W - pad" :y2="H - pad" stroke="var(--border)" />
          <line :x1="pad" :y1="pad" :x2="pad" :y2="H - pad" stroke="var(--border)" />
          <polyline v-for="(s, i) in seriesPaths" :key="s.key" :points="s.points" fill="none"
            :stroke="i === 0 ? 'var(--faint)' : 'var(--accent)'"
            :stroke-dasharray="i === 0 ? '4 3' : '0'" stroke-width="2" />
        </svg>
        <div class="flex items-center gap-4 justify-center text-[11px] text-muted mt-1">
          <span v-for="(s, i) in seriesPaths" :key="s.key" class="inline-flex items-center gap-1.5">
            <span class="inline-block w-3 h-[2px]" :style="{ background: i === 0 ? 'var(--faint)' : 'var(--accent)' }" />
            {{ s.label }}
          </span>
        </div>
      </div>

      <div class="card-surface overflow-x-auto">
        <table class="data-table">
          <thead>
            <tr>
              <th v-for="c in columns" :key="c.fieldname">{{ c.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in rows" :key="i">
              <td v-for="c in columns" :key="c.fieldname" class="tnum"
                :class="c.fieldname === columns[0].fieldname ? 'text-app' : 'text-muted'"
                v-html="fmt(r[c.fieldname])" />
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { call } from 'frappe-ui'

const W = 640, H = 200, pad = 28
const reports = ref([])
const projects = ref([])
const sprints = ref([])
const reportKey = ref('burndown')
const project = ref(null)
const sprint = ref(null)
const columns = ref([])
const rows = ref([])
const chart = ref(null)
const loading = ref(true)
const error = ref('')

const current = computed(() => reports.value.find((r) => r.key === reportKey.value))

function fmt(v) {
  if (v === null || v === undefined || v === '') return '—'
  return String(v)
}

const points = computed(() => (chart.value ? rows.value.filter((r) => r[chart.value.x] != null) : []))

const seriesPaths = computed(() => {
  if (!chart.value || points.value.length < 2) return []
  const keys = chart.value.series
  const all = points.value.flatMap((r) => keys.map((k) => Number(r[k] || 0)))
  const max = Math.max(...all, 1)
  const n = points.value.length
  return keys.map((k) => ({
    key: k,
    label: (columns.value.find((c) => c.fieldname === k) || {}).label || k,
    points: points.value.map((r, i) => {
      const x = pad + (i * (W - pad * 2)) / (n - 1)
      const y = H - pad - (Number(r[k] || 0) / max) * (H - pad * 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    }).join(' '),
  }))
})

async function onProject() {
  sprint.value = null
  sprints.value = await call('pulse.api.reports.sprint_options', { project: project.value }).catch(() => [])
  load()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const r = await call('pulse.api.reports.run_report', {
      report: reportKey.value, project: project.value, sprint: sprint.value,
    })
    columns.value = r.columns
    rows.value = r.data
    chart.value = r.chart
  } catch (e) {
    error.value = e?.messages?.[0] || 'Could not generate this report.'
    columns.value = []; rows.value = []
  }
  loading.value = false
}

onMounted(async () => {
  const [rs, ps] = await Promise.all([
    call('pulse.api.reports.list_reports').catch(() => []),
    call('pulse.api.spa.get_projects').catch(() => []),
  ])
  reports.value = rs
  projects.value = ps
  sprints.value = await call('pulse.api.reports.sprint_options').catch(() => [])
  load()
})
</script>

<style scoped>
.ctl { background: var(--surface); border: 1px solid var(--border); color: var(--text); font-size: 12px; border-radius: 9px; padding: 7px 10px; outline: none; }
</style>
