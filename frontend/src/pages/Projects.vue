<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-2xl font-bold">Projects</h1>
      <button v-if="canWrite" @click="openEntity('Project')" class="btn-primary">
        <Plus class="w-3.5 h-3.5" /> New project
      </button>
    </div>

    <div v-if="loading" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      <div v-for="n in 6" :key="n" class="card-surface p-4"><Skeleton width="50%" height="14px" /><div class="mt-3"><Skeleton width="90%" height="11px" /></div></div>
    </div>

    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      <div v-for="p in projects" :key="p.name" @click="openEntity('Project', p.name)"
        class="card-surface p-4 hover:border-accent cursor-pointer transition-colors">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-2 min-w-0">
            <span class="mono text-[9px] font-bold px-1.5 py-1 rounded" :style="{ background: 'var(--surface-2)', color: 'var(--accent)' }">{{ (p.pulse_project_key || '·').slice(0,3) }}</span>
            <div class="font-medium text-app truncate">{{ p.project_name || p.name }}</div>
          </div>
          <StatusPill v-if="p.status" :value="p.status" />
        </div>
        <p class="text-xs text-muted mt-2.5 line-clamp-2">{{ p.notes || 'No description' }}</p>
        <div class="flex items-center gap-3 mt-3 text-[11px] text-faint">
          <span class="tnum">{{ p.taskCount }} tasks</span>
          <button @click.stop="goBoard(p.name)" class="ml-auto text-accent hover:underline">Open board →</button>
        </div>
      </div>
      <div v-if="!projects.length" class="col-span-full py-16 text-center text-faint">No projects yet. Create your first project.</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { canWrite } from '@/utils/access'
import { useRouter } from 'vue-router'
import { call } from 'frappe-ui'
import StatusPill from '@/ui/StatusPill.vue'
import Skeleton from '@/ui/Skeleton.vue'
import { openEntity, entityState } from '@/ui/entity'
import Plus from '~icons/lucide/plus'

const router = useRouter()
const loading = ref(true)
const projects = ref([])

function goBoard(name) { router.push(`/board?project=${encodeURIComponent(name)}`) }

async function reload() {
  loading.value = true
  const list = await call('pulse.api.spa.get_projects').catch(() => [])
  for (const p of list) p.taskCount = p.task_count
  projects.value = list
  loading.value = false
}
watch(() => entityState.saved, reload)
onMounted(reload)
</script>

<style scoped>
.new-btn { background: var(--accent); transition: filter 0.12s; }
.new-btn:hover { filter: brightness(1.08); }
</style>
