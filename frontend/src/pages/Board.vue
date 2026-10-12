<template>
  <div class="h-full flex flex-col">
    <!-- Header -->
    <div class="px-6 pt-5 pb-3 border-b border-soft">
      <div class="flex items-center justify-between gap-3">
        <div class="flex items-baseline gap-2.5">
          <h1 class="text-2xl font-bold">Board</h1>
          <span class="text-xs text-faint tnum">{{ visibleCount }} of {{ board.total }}</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="flex rounded-md border border-app overflow-hidden text-xs">
            <button @click="view = 'board'" :class="view === 'board' ? 'seg-on' : 'seg'"><SquareKanban class="w-3.5 h-3.5" /></button>
            <button @click="view = 'list'" :class="view === 'list' ? 'seg-on' : 'seg'"><List class="w-3.5 h-3.5" /></button>
          </div>
          <select v-model="project" @change="load" class="ctl">
            <option :value="null">All projects</option>
            <option v-for="p in projects" :key="p.name" :value="p.name">{{ p.project_name || p.name }}</option>
          </select>
          <button v-if="canWrite" @click="openCreate({ project })" class="btn-primary">
            <Plus class="w-3.5 h-3.5" /> New task
          </button>
        </div>
      </div>

      <!-- Filter bar -->
      <div class="flex items-center gap-2 mt-3">
        <div class="relative">
          <Search class="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
          <input v-model="filters.q" placeholder="Search tasks" class="ctl pl-8 w-52" />
        </div>
        <select v-model="filters.type" class="ctl"><option value="">All types</option><option v-for="t in issueTypes" :key="t">{{ t }}</option></select>
        <select v-model="filters.priority" class="ctl"><option value="">All priority</option><option>Urgent</option><option>Critical</option><option>High</option><option>Medium</option><option>Low</option></select>
        <select v-model="filters.assignee" class="ctl"><option value="">Anyone</option><option v-for="a in assignees" :key="a" :value="a">{{ a.split('@')[0] }}</option></select>
        <button v-if="hasFilters" @click="clearFilters" class="text-xs text-faint hover:text-app px-2 py-1.5 inline-flex items-center gap-1"><X class="w-3 h-3" />Clear</button>
      </div>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading" class="flex gap-3 p-6 overflow-hidden">
      <div v-for="n in 5" :key="n" class="w-[264px] shrink-0">
        <Skeleton width="120px" height="14px" />
        <div class="mt-3 space-y-2">
          <div v-for="m in 3" :key="m" class="card-surface p-3">
            <Skeleton width="46px" height="10px" /><div class="mt-2"><Skeleton width="90%" height="12px" /></div>
            <div class="mt-3"><Skeleton width="60%" height="10px" /></div>
          </div>
        </div>
      </div>
    </div>

    <!-- BOARD -->
    <div v-else-if="view === 'board'" class="flex gap-3 overflow-x-auto flex-1 px-6 py-4">
      <div v-for="col in cols" :key="col.name" class="w-[264px] shrink-0 flex flex-col"
        @dragover.prevent="dragOver = col.name" @dragleave="dragOver === col.name && (dragOver = null)" @drop="onDrop(col.name)">
        <div class="flex items-center gap-2 px-1.5 pb-2">
          <span class="w-1.5 h-1.5 rounded-full" :style="{ background: colColor(col.name) }" />
          <span class="text-[12.5px] font-medium text-app">{{ col.name }}</span>
          <span class="text-[11px] text-faint tnum ml-1">{{ col.tasks.length }}</span>
          <button @click="startAdd(col.name)" class="ml-auto p-1 rounded hover-app text-faint" title="Add task"><Plus class="w-3.5 h-3.5" /></button>
        </div>
        <div class="flex flex-col gap-2 rounded-lg p-1.5 transition-colors flex-1 min-h-[60px]"
          :style="{ background: dragOver === col.name ? 'var(--surface-2)' : 'transparent' }">
          <!-- quick add -->
          <div v-if="adding === col.name" class="rounded-lg border border-accent bg-surface p-2.5" style="border-color:var(--accent)">
            <input ref="addInput" v-model="newSubject" @keyup.enter="submitAdd(col.name)" @keyup.esc="cancelAdd" @blur="cancelAdd"
              placeholder="What needs doing?" class="w-full bg-transparent text-[13px] outline-none" />
            <div class="text-[10px] text-faint mt-1.5">Enter to add · Esc to cancel</div>
          </div>

          <div v-for="t in col.tasks" :key="t.name" draggable="true" @dragstart="dragTask = t" @click="open(t.name)"
            class="card group card-surface p-3 cursor-pointer">
            <div class="flex items-center gap-2 mb-1.5">
              <span class="mono text-[10.5px] text-faint">{{ t.issue_key }}</span>
              <TypeTag :value="t.task_type" class="ml-auto" />
            </div>
            <div class="text-[13px] leading-snug text-app">{{ t.subject }}</div>
            <div class="flex items-center gap-2.5 mt-2.5">
              <PriorityDot :value="t.priority" />
              <div class="ml-auto flex -space-x-1.5">
                <Avatar v-for="a in t.assignees" :key="a" :name="a" :size="20" />
              </div>
            </div>
          </div>
          <button v-if="!col.tasks.length && adding !== col.name" @click="startAdd(col.name)"
            class="text-[12px] text-faint hover:text-muted py-2 text-left px-1">+ Add task</button>
        </div>
      </div>
    </div>

    <!-- LIST -->
    <div v-else class="flex-1 overflow-auto px-6 py-4">
      <div v-for="col in cols" :key="col.name" class="mb-5">
        <div class="flex items-center gap-2 mb-1.5 sticky top-0 bg-app py-1">
          <span class="w-1.5 h-1.5 rounded-full" :style="{ background: colColor(col.name) }" />
          <span class="text-[13px] font-medium">{{ col.name }}</span>
          <span class="text-[11px] text-faint tnum">{{ col.tasks.length }}</span>
        </div>
        <div v-for="t in col.tasks" :key="t.name" @click="open(t.name)"
          class="flex items-center gap-3 px-2 py-2 rounded-md hover-app cursor-pointer">
          <span class="mono text-[11px] text-faint w-16 shrink-0">{{ t.issue_key }}</span>
          <TypeTag :value="t.task_type" />
          <span class="flex-1 truncate text-[13px]">{{ t.subject }}</span>
          <PriorityDot :value="t.priority" />
          <div class="flex -space-x-1.5 w-16 justify-end">
            <Avatar v-for="a in t.assignees" :key="a" :name="a" :size="20" />
          </div>
        </div>
      </div>
    </div>

    <TaskDrawer :task-id="openId" @close="openId = null" @changed="load" @open="open" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { call } from 'frappe-ui'
import { io } from 'socket.io-client'
import TaskDrawer from '@/components/TaskDrawer.vue'
import Avatar from '@/ui/Avatar.vue'
import TypeTag from '@/ui/TypeTag.vue'
import PriorityDot from '@/ui/PriorityDot.vue'
import Skeleton from '@/ui/Skeleton.vue'
import { toast } from '@/ui/toast'
import { openCreate, createState } from '@/ui/create'
import SquareKanban from '~icons/lucide/square-kanban'
import List from '~icons/lucide/list'
import Search from '~icons/lucide/search'
import Plus from '~icons/lucide/plus'
import X from '~icons/lucide/x'

const canWrite = window.can_write !== false

const route = useRoute()
const loading = ref(true)
const view = ref('board')
const board = ref({ columns: [], total: 0 })
const projects = ref([])
const issueTypes = ref([])
const project = ref(route.query.project || null)
const dragTask = ref(null)
const dragOver = ref(null)
const openId = ref(null)
const adding = ref(null)
const newSubject = ref('')
const addInput = ref(null)
const filters = reactive({ q: '', type: '', priority: '', assignee: '' })

const COL_COLORS = { Backlog: '#8994a3', 'To Do': '#b491ff', 'In Progress': '#f5b45a', 'In Review': '#6aa9ff', Done: '#34d399' }
function colColor(c) { return COL_COLORS[c] || '#8994a3' }

const assignees = computed(() => {
  const s = new Set()
  for (const c of board.value.columns) for (const t of c.tasks) for (const a of (t.assignees || [])) s.add(a)
  return [...s]
})
const hasFilters = computed(() => filters.q || filters.type || filters.priority || filters.assignee)
function clearFilters() { filters.q = ''; filters.type = ''; filters.priority = ''; filters.assignee = '' }

const cols = computed(() => board.value.columns.map((c) => ({
  name: c.name,
  tasks: c.tasks.filter((t) => {
    if (filters.q && !(`${t.issue_key} ${t.subject}`.toLowerCase().includes(filters.q.toLowerCase()))) return false
    if (filters.type && t.task_type !== filters.type) return false
    if (filters.priority && t.priority !== filters.priority) return false
    if (filters.assignee && !(t.assignees || []).includes(filters.assignee)) return false
    return true
  }),
})))
const visibleCount = computed(() => cols.value.reduce((n, c) => n + c.tasks.length, 0))

async function load() {
  loading.value = true
  const [b, ps, its] = await Promise.all([
    call('pulse.api.spa.get_board', { project: project.value }),
    projects.value.length ? Promise.resolve(projects.value)
      : call('frappe.client.get_list', { doctype: 'Project', fields: ['name', 'project_name'], limit_page_length: 0 }),
    issueTypes.value.length ? Promise.resolve(issueTypes.value)
      : call('frappe.client.get_list', { doctype: 'Task Type', fields: ['name'], limit_page_length: 0 }).then((r) => r.map((x) => x.name)),
  ])
  board.value = b; projects.value = ps; issueTypes.value = its
  loading.value = false
}

async function onDrop(colName) {
  dragOver.value = null
  const t = dragTask.value; dragTask.value = null
  if (!t) return
  const fromCol = board.value.columns.find((c) => c.tasks.some((x) => x.name === t.name))
  if (fromCol?.name === colName) return
  for (const c of board.value.columns) {
    const i = c.tasks.findIndex((x) => x.name === t.name)
    if (i >= 0) c.tasks.splice(i, 1)
  }
  board.value.columns.find((c) => c.name === colName)?.tasks.unshift(t)
  try {
    await call('pulse.api.spa.update_task_state', { task: t.name, state: colName })
    toast.success(`${t.issue_key} moved to ${colName}`)
  } catch (e) { toast.error('Could not move task'); load() }
}

function startAdd(col) { adding.value = col; newSubject.value = ''; nextTick(() => addInput.value?.[0]?.focus?.() || addInput.value?.focus?.()) }
function cancelAdd() { setTimeout(() => { adding.value = null }, 120) }
async function submitAdd(col) {
  const subject = newSubject.value.trim()
  if (!subject) return
  const proj = project.value || projects.value[0]?.name
  if (!proj) { toast.error('Pick a project first'); return }
  try {
    const t = await call('pulse.api.spa.create_task', { project: proj, subject, state: col })
    board.value.columns.find((c) => c.name === col)?.tasks.unshift({ ...t, assignees: [] })
    board.value.total++
    newSubject.value = ''
    toast.success(`Created ${t.issue_key}`)
  } catch (e) { toast.error('Could not create task') }
}

function open(name) { openId.value = name }
// reload when an issue is created from the global New Issue dialog
watch(() => createState.created, load)

// --- real-time: refresh the board when anyone changes it (needs socketio) ---
let socket = null
let rtTimer = null

// Frappe's socketio is per-site: the socket.io NAMESPACE must equal the site
// name, and the backend publishes events under the real site name (e.g.
// "pulse.local"). When the app is reached by IP the server would otherwise
// derive the site from the Origin hostname and we'd sit in the wrong namespace,
// so we state the site explicitly via X-Frappe-Site-Name (honoured first by
// the socketio auth middleware). That header only rides on the polling
// handshake, hence polling-first — socket.io upgrades to websocket after.
function realtimeSite() {
  return window.sitename || location.hostname
}
function realtimeUrl() {
  const port = window.socketio_port || 9000
  return `${location.protocol}//${location.hostname}:${port}/${realtimeSite()}`
}

function connectRealtime() {
  const url = realtimeUrl()
  try {
    socket = io(url, {
      withCredentials: true,
      transports: ['polling', 'websocket'],
      transportOptions: { polling: { extraHeaders: { 'X-Frappe-Site-Name': realtimeSite() } } },
    })
    socket.on('connect', () => { window.__pulseRealtime = `connected ${url}` })
    socket.on('connect_error', (e) => {
      // realtime is optional — surface why instead of failing silently
      window.__pulseRealtime = `error: ${e?.message || e}`
      console.warn('[pulse] realtime unavailable:', e?.message || e, url)
    })
    socket.on('pulse:board', () => { clearTimeout(rtTimer); rtTimer = setTimeout(load, 400) })
  } catch (e) {
    window.__pulseRealtime = `threw: ${e}`
    console.warn('[pulse] realtime init failed', e)
  }
}
onMounted(() => { load(); connectRealtime() })
onUnmounted(() => { try { socket && socket.disconnect() } catch (e) {} clearTimeout(rtTimer) })
</script>

<style scoped>
.ctl { background: var(--surface); border: 1px solid var(--border); color: var(--text); font-size: 12px; border-radius: 9px; padding: 7px 10px; outline: none; }
.ctl:focus { border-color: var(--accent); }
.seg, .seg-on { padding: 6px 10px; display: grid; place-items: center; }
.seg { color: var(--muted); background: var(--surface); }
.seg-on { color: #fff; background: var(--accent); }
.card { transition: transform 0.13s ease, border-color 0.13s ease; }
.card:hover { transform: translateY(-1px); border-color: var(--accent); }
.new-btn { background: var(--accent); transition: filter 0.12s; }
.new-btn:hover { filter: brightness(1.08); }
</style>
