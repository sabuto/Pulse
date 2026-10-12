<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-1">
      <h1 class="text-2xl font-bold">To Do</h1>
      <span class="tele text-[10px] text-faint">{{ tasks.length }} open</span>
    </div>
    <p class="text-xs text-faint mb-5">Everything assigned to you that isn't done — across all projects. Tick to complete.</p>

    <div v-if="loading" class="space-y-2">
      <div v-for="n in 6" :key="n" class="flex items-center gap-3 py-2 border-b border-soft">
        <Skeleton width="16px" height="16px" /><Skeleton width="52px" height="12px" /><Skeleton width="45%" height="13px" />
      </div>
    </div>

    <div v-else>
      <div v-for="g in groups" :key="g.label">
        <div v-if="g.items.length" class="mb-5">
          <div class="tele text-[10px] font-semibold mb-1.5 flex items-center gap-1.5" :class="g.tone">
            <span>//</span>{{ g.label }}<span class="text-faint">({{ g.items.length }})</span>
          </div>
          <div v-for="t in g.items" :key="t.name"
            class="flex items-center gap-3 py-2 border-b border-soft hover-app cursor-pointer"
            @click="openId = t.name">
            <input v-if="canWrite" type="checkbox" class="shrink-0 cursor-pointer" title="Mark done" @click.stop="complete(t)" />
            <span class="mono text-[11px] text-faint w-16 shrink-0">{{ t.issue_key }}</span>
            <span class="flex-1 truncate text-app">{{ t.subject }}</span>
            <PriorityDot :value="t.priority" />
            <span class="text-xs text-muted w-32 truncate hidden md:block">{{ t.project }}</span>
            <span class="text-xs w-24 text-right shrink-0" :class="g.tone">{{ due(t) || '—' }}</span>
          </div>
        </div>
      </div>
      <div v-if="!tasks.length" class="py-16 text-center text-faint">Nothing assigned to you right now.</div>
    </div>

    <TaskDrawer :task-id="openId" @close="openId = null" @changed="reload" @open="openId = $event" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { canWrite } from '@/utils/access'
import { askResolution } from '@/ui/resolution'
import { call } from 'frappe-ui'
import TaskDrawer from '@/components/TaskDrawer.vue'
import PriorityDot from '@/ui/PriorityDot.vue'
import Skeleton from '@/ui/Skeleton.vue'
import { toast } from '@/ui/toast'
import { createState } from '@/ui/create'

const loading = ref(true)
const tasks = ref([])
const openId = ref(null)

function iso(d) { return new Date(d).toISOString().slice(0, 10) }
// exp_end_date may arrive as "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS" — keep the date part
function due(t) { return (t.exp_end_date || '').slice(0, 10) }

const groups = computed(() => {
  const today = iso(Date.now())
  const weekEnd = iso(Date.now() + 7 * 864e5)
  const b = { overdue: [], today: [], week: [], later: [], none: [] }
  for (const t of tasks.value) {
    const d = due(t) // normalise: the field can come back with a time component
    if (!d) b.none.push(t)
    else if (d < today) b.overdue.push(t)
    else if (d === today) b.today.push(t)
    else if (d <= weekEnd) b.week.push(t)
    else b.later.push(t)
  }
  return [
    { label: 'Overdue', items: b.overdue, tone: 'text-red-500' },
    { label: 'Due today', items: b.today, tone: 'text-accent' },
    { label: 'This week', items: b.week, tone: 'text-muted' },
    { label: 'Later', items: b.later, tone: 'text-muted' },
    { label: 'No due date', items: b.none, tone: 'text-faint' },
  ]
})

async function reload() {
  tasks.value = await call('pulse.api.spa.my_todos').catch(() => [])
  loading.value = false
}

async function complete(t) {
  const note = await askResolution(t)
  if (note === null) return  // cancelled
  try {
    await call('pulse.api.spa.update_task_state',
      { task: t.name, state: 'Done', ...(note ? { resolution: note } : {}) })
    tasks.value = tasks.value.filter((x) => x.name !== t.name)
    toast.success(`${t.issue_key} completed`)
  } catch (e) {
    toast.error('Could not complete task')
    reload()
  }
}

watch(() => createState.created, reload)
onMounted(reload)
</script>
