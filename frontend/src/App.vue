<template>
  <div class="flex h-full bg-app text-app text-sm">
    <!-- Sidebar -->
    <aside class="flex flex-col w-[232px] shrink-0 border-r border-app bg-surface">
      <div class="flex items-center gap-2.5 px-4 h-14 border-b border-app">
        <div class="w-[30px] h-[30px] rounded-xl grid place-items-center font-bold text-[15px]" style="background:var(--accent);color:var(--on-accent)">P</div>
        <div class="flex flex-col leading-none">
          <span class="text-[16px] font-bold tracking-tight">Pulse</span>
          <span class="text-[10px] text-faint mt-[3px]">Project management</span>
        </div>
      </div>

      <div v-if="canWrite" class="px-2.5 pt-3">
        <button @click="openCreate()" class="new-btn w-full flex items-center justify-center gap-2 py-2.5 text-[13px] font-semibold">
          <Plus class="w-4 h-4" /> New task
        </button>
      </div>

      <nav class="flex-1 px-2 py-3 space-y-5 overflow-y-auto">
        <div v-for="group in nav" :key="group.section">
          <div class="px-2.5 pb-1.5 tele text-[10px] font-semibold text-faint flex items-center gap-1.5">{{ group.section }}</div>
          <template v-for="item in group.items" :key="item.to || item.href">
            <a v-if="item.href" :href="item.href" target="_blank"
              class="nav-item flex items-center gap-2.5 px-2.5 py-[7px] rounded-md text-[13px] hover-app">
              <component :is="item.icon" class="w-[15px] h-[15px] shrink-0" />
              <span>{{ item.label }}</span>
            </a>
            <router-link v-else :to="item.to"
              class="nav-item flex items-center gap-2.5 px-2.5 py-[7px] rounded-md text-[13px] hover-app"
              active-class="active">
              <component :is="item.icon" class="w-[15px] h-[15px] shrink-0" />
              <span>{{ item.label }}</span>
            </router-link>
          </template>
        </div>

        <div>
          <div class="px-2.5 pb-1.5 tele text-[10px] font-semibold text-faint flex items-center gap-1.5">Projects</div>
          <router-link v-for="p in projects" :key="p.name" :to="`/board?project=${encodeURIComponent(p.name)}`"
            class="nav-item flex items-center gap-2.5 px-2.5 py-[7px] rounded-md text-[13px] hover-app">
            <span class="w-[18px] h-[18px] grid place-items-center rounded-[5px] mono text-[8.5px] font-bold shrink-0"
              :style="{ background: 'var(--surface-2)', color: 'var(--accent)' }">{{ (p.pulse_project_key || '·').slice(0, 3) }}</span>
            <span class="truncate">{{ p.project_name || p.name }}</span>
          </router-link>
        </div>
      </nav>
      <div class="px-3 py-2.5 border-t border-soft flex items-center justify-between">
        <span class="flex items-center gap-2 min-w-0">
          <Avatar :name="user" :size="22" />
          <span class="text-[12px] text-muted truncate mono">{{ shortUser }}</span>
        </span>
        <button @click="onToggle" class="p-1.5 rounded-md hover-app text-muted" :title="theme === 'dark' ? 'Light mode' : 'Dark mode'">
          <Moon v-if="theme === 'dark'" class="w-[15px] h-[15px]" />
          <Sun v-else class="w-[15px] h-[15px]" />
        </button>
      </div>
    </aside>

    <main class="flex-1 overflow-auto min-w-0">
      <router-view />
    </main>

    <CreateIssueModal />
    <ResolutionDialog />
    <EntityForm />
    <Toaster />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { call } from 'frappe-ui'
import { theme, toggleTheme } from './theme'
import { openCreate } from './ui/create'
import Avatar from './ui/Avatar.vue'
import Toaster from './ui/Toaster.vue'
import CreateIssueModal from './components/CreateIssueModal.vue'
import ResolutionDialog from './components/ResolutionDialog.vue'

// Pulse Viewer is read-only; the server enforces it, this just hides the controls.
const canWrite = window.can_write !== false
import EntityForm from './components/EntityForm.vue'
import Plus from '~icons/lucide/plus'
import House from '~icons/lucide/house'
import LayoutDashboard from '~icons/lucide/layout-dashboard'
import ChartColumn from '~icons/lucide/chart-column'
import FileBarChart from '~icons/lucide/file-bar-chart'
import SquareCheckBig from '~icons/lucide/square-check-big'
import ListChecks from '~icons/lucide/list-checks'
import SquareKanban from '~icons/lucide/square-kanban'
import List from '~icons/lucide/list'
import CalendarDays from '~icons/lucide/calendar-days'
import Repeat from '~icons/lucide/repeat'
import Folder from '~icons/lucide/folder'
import Layers from '~icons/lucide/layers'
import Zap from '~icons/lucide/zap'
import Tag from '~icons/lucide/tag'
import Target from '~icons/lucide/target'
import ShieldAlert from '~icons/lucide/shield-alert'
import Users from '~icons/lucide/users'
import RefreshCw from '~icons/lucide/refresh-cw'
import FileText from '~icons/lucide/file-text'
import Clock from '~icons/lucide/clock'
import ScrollText from '~icons/lucide/scroll-text'
import Settings from '~icons/lucide/settings'
import Sun from '~icons/lucide/sun'
import Moon from '~icons/lucide/moon'

const user = ref('')
const projects = ref([])
const shortUser = computed(() => (user.value || '').split('@')[0])

const nav = [
  { section: 'Work', items: [
    { to: '/', label: 'Home', icon: House },
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/analytics', label: 'Analytics', icon: ChartColumn },
    { to: '/reports', label: 'Reports', icon: FileBarChart },
    { to: '/todo', label: 'To Do', icon: ListChecks },
    { to: '/my-work', label: 'My Work', icon: SquareCheckBig },
    { to: '/board', label: 'Board', icon: SquareKanban },
    { to: '/backlog', label: 'Backlog', icon: List },
    { to: '/sprints', label: 'Sprints', icon: CalendarDays },
    { to: '/recurring', label: 'Recurring', icon: Repeat },
    { to: '/projects', label: 'Projects', icon: Folder },
  ] },
  { section: 'Plan', items: [
    { to: '/epics', label: 'Epics', icon: Zap },
    { to: '/releases', label: 'Releases', icon: Tag },
    { to: '/m/portfolio', label: 'Portfolio', icon: Layers },
    { to: '/m/okrs', label: 'OKRs', icon: Target },
    { to: '/m/risks', label: 'Risks', icon: ShieldAlert },
  ] },
  { section: 'Collaborate', items: [
    { to: '/m/meetings', label: 'Meetings', icon: Users },
    { to: '/m/retros', label: 'Retrospectives', icon: RefreshCw },
    { to: '/m/documents', label: 'Documents', icon: FileText },
    { to: '/m/timesheets', label: 'Timesheets', icon: Clock },
  ] },
  { section: 'System', items: [
    { to: '/audit', label: 'Audit Logs', icon: ScrollText },
    { href: '/app/pulse-settings', label: 'Settings', icon: Settings },
  ] },
]

function onToggle() { toggleTheme() }

onMounted(async () => {
  try { user.value = await call('frappe.auth.get_logged_user') } catch (e) { user.value = '' }
  projects.value = await call('pulse.api.spa.get_projects').catch(() => [])
})
</script>

<style scoped>
.nav-item { color: var(--muted); transition: color 0.12s, background 0.12s; }
.nav-item:hover { color: var(--text); }
.nav-item.active { color: var(--text); background: var(--surface-2); font-weight: 500; }
.nav-item.active :deep(svg) { color: var(--accent); }
.new-btn { background: var(--accent); transition: filter 0.12s; }
.new-btn:hover { filter: brightness(1.08); }
</style>
