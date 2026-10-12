<template>
  <div class="p-6">
    <h1 class="text-2xl font-bold mb-4">My Work</h1>

    <div v-if="loading" class="space-y-2">
      <div v-for="n in 6" :key="n" class="flex items-center gap-4 py-2 border-b border-soft">
        <Skeleton width="52px" height="12px" /><Skeleton width="40%" height="13px" />
        <Skeleton width="60px" height="16px" radius="5px" /><div class="ml-auto"><Skeleton width="80px" height="12px" /></div>
      </div>
    </div>

    <div v-else class="card-surface overflow-x-auto">
      <table class="data-table">
        <thead>
          <tr>
            <th class="w-16">Key</th>
            <th>Issue</th>
            <th class="w-24">Type</th>
            <th class="w-28">Priority</th>
            <th class="w-32">Status</th>
            <th>Project</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in tasks" :key="t.name" class="cursor-pointer" @click="openId = t.name">
            <td class="mono text-[11px] text-faint">{{ t.issue_key }}</td>
            <td class="font-medium text-app">{{ t.subject }}</td>
            <td><TypeTag :value="t.task_type" /></td>
            <td><PriorityDot :value="t.priority" show-label /></td>
            <td><StatusPill :value="t.status" /></td>
            <td class="text-muted">{{ t.project || '-' }}</td>
          </tr>
          <tr v-if="!tasks.length"><td colspan="6" class="py-16 text-center text-faint">No tasks assigned to you yet.</td></tr>
        </tbody>
      </table>
    </div>
    <TaskDrawer :task-id="openId" @close="openId = null" @changed="reload" @open="openId = $event" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { call } from 'frappe-ui'
import TaskDrawer from '@/components/TaskDrawer.vue'
import TypeTag from '@/ui/TypeTag.vue'
import PriorityDot from '@/ui/PriorityDot.vue'
import StatusPill from '@/ui/StatusPill.vue'
import Skeleton from '@/ui/Skeleton.vue'

const loading = ref(true)
const tasks = ref([])
const openId = ref(null)

async function reload() {
  const me = await call('frappe.auth.get_logged_user')
  tasks.value = await call('pulse.api.spa.list_tasks', { which: 'mine' })
  loading.value = false
}
onMounted(reload)
</script>
