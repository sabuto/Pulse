<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-2xl font-bold">Sprints</h1>
      <button v-if="canWrite" @click="openEntity('Pulse Sprint')" class="btn-primary">
        <Plus class="w-3.5 h-3.5" /> New sprint
      </button>
    </div>

    <div v-if="loading" class="space-y-2">
      <div v-for="n in 4" :key="n" class="card-surface p-4"><Skeleton width="40%" height="14px" /><div class="mt-2"><Skeleton width="70%" height="11px" /></div></div>
    </div>

    <div v-else class="space-y-2.5">
      <div v-for="s in sprints" :key="s.name" @click="openEntity('Pulse Sprint', s.name)"
        class="card-surface p-4 hover:border-accent cursor-pointer transition-colors">
        <div class="flex items-center justify-between gap-2">
          <div class="font-medium text-app">{{ s.sprint_name || s.name }}</div>
          <StatusPill :value="s.status" />
        </div>
        <div class="flex items-center gap-5 mt-2 text-xs text-muted">
          <span class="inline-flex items-center gap-1.5"><CalendarDays class="w-3.5 h-3.5" />{{ s.start_date || '?' }} → {{ s.end_date || '?' }}</span>
          <span>{{ s.project }}</span>
          <span class="ml-auto tnum">{{ s.taskCount }} tasks</span>
        </div>
      </div>
      <div v-if="!sprints.length" class="py-16 text-center text-faint">No sprints yet. Create your first sprint.</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { canWrite } from '@/utils/access'
import { call } from 'frappe-ui'
import StatusPill from '@/ui/StatusPill.vue'
import Skeleton from '@/ui/Skeleton.vue'
import { openEntity, entityState } from '@/ui/entity'
import CalendarDays from '~icons/lucide/calendar-days'
import Plus from '~icons/lucide/plus'

const loading = ref(true)
const sprints = ref([])

async function reload() {
  loading.value = true
  const list = await call('pulse.api.spa.list_sprints').catch(() => [])
  for (const s of list) s.taskCount = s.task_count
  sprints.value = list
  loading.value = false
}
watch(() => entityState.saved, reload)
onMounted(reload)
</script>

<style scoped>
.new-btn { background: var(--accent); transition: filter 0.12s; }
.new-btn:hover { filter: brightness(1.08); }
</style>
