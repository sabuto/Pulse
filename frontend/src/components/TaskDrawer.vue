<template>
  <transition name="slide">
    <div v-if="taskId" class="fixed inset-0 z-40 flex justify-end">
      <!-- Click outside the drawer to close it. It's the backdrop's own click (not the
           wrapper's) so dragging a text selection out of the drawer doesn't close it. -->
      <div class="absolute inset-0 bg-black/40" @click="$emit('close')" />
      <aside class="relative w-[800px] max-w-full h-full bg-surface text-app border-l border-app shadow-2xl overflow-y-auto">
        <div v-if="task" class="p-5">
          <div class="flex items-center justify-between">
            <span class="text-xs font-mono px-2 py-0.5 rounded bg-surface-2 text-accent">{{ task.issue_key || task.name }}</span>
            <button class="text-muted hover:text-app" @click="$emit('close')">Close</button>
          </div>

          <input v-model="task.subject" @change="save('subject', task.subject)" :readonly="!canWrite"
            class="mt-2 w-full text-lg font-semibold bg-transparent outline-none border-b border-transparent focus:border-app" />

          <div class="grid grid-cols-2 gap-3 mt-4 text-sm">
            <label class="block">
              <span class="text-xs text-muted">Type</span>
              <select v-model="task.task_type" @change="save('task_type', task.task_type)" :disabled="!canWrite" class="field">
                <option v-for="t in issueTypes" :key="t" :value="t">{{ t }}</option>
              </select>
            </label>
            <label class="block">
              <span class="text-xs text-muted">Priority</span>
              <select v-model="task.priority" @change="save('priority', task.priority)" :disabled="!canWrite" class="field">
                <option>Low</option><option>Medium</option><option>High</option><option>Critical</option>
              </select>
            </label>
            <label class="block">
              <span class="text-xs text-muted">Due date</span>
              <input type="date" v-model="task.exp_end_date" @change="save('exp_end_date', task.exp_end_date)" :disabled="!canWrite" class="field" />
            </label>
          </div>

          <!-- Epic + App + Release -->
          <div class="grid grid-cols-3 gap-3 mt-3 text-sm">
            <label class="block">
              <span class="text-xs text-muted">Epic</span>
              <select v-model="task.pulse_epic" @change="save('pulse_epic', task.pulse_epic)" :disabled="!canWrite" class="field">
                <option :value="null">— none —</option>
                <option v-for="e in epics" :key="e.name" :value="e.name">
                  {{ e.issue_key ? e.issue_key + ' · ' : '' }}{{ e.subject }}
                </option>
              </select>
            </label>
            <label class="block">
              <span class="text-xs text-muted">App</span>
              <select v-model="task.pulse_release_app" @change="save('pulse_release_app', task.pulse_release_app || '')" :disabled="!canWrite" class="field">
                <option :value="null">— none —</option>
                <option v-for="a in appOptions" :key="a" :value="a">{{ a }}</option>
              </select>
            </label>
            <label class="block">
              <span class="text-xs text-muted">Release</span>
              <input v-model="task.pulse_release" list="pulse-releases" placeholder="e.g. v1.2"
                @change="save('pulse_release', task.pulse_release)" :readonly="!canWrite" class="field" />
              <datalist id="pulse-releases">
                <option v-for="name in releaseSuggestions" :key="name" :value="name" />
              </datalist>
            </label>
          </div>

          <div class="mt-4">
            <span class="text-xs text-muted">Description</span>
            <RichText :key="task.name" v-model="task.description" :task-name="task.name" :editable="canWrite"
              :placeholder="canWrite ? 'Add a description — paste images straight in' : ''"
              @commit="save('description', task.description)" />
          </div>

          <!-- Resolution: what was done (also in the completion email) -->
          <div v-if="task.workflow_state === 'Done' || task.resolution" class="mt-4">
            <span class="text-xs text-muted">Resolution — what was done</span>
            <textarea v-model="task.resolution" @change="save('pulse_resolution', task.resolution)"
              rows="3" :readonly="!canWrite" class="field resize-y" placeholder="Optional" />
          </div>

          <!-- Bug report details (only on tasks raised via Report Bug) -->
          <div v-if="task.bug" class="mt-4 rounded-md border border-app bg-surface-2 p-3">
            <div class="text-xs font-semibold text-muted mb-2">Bug report</div>
            <dl class="grid grid-cols-[110px_1fr] gap-x-3 gap-y-1 text-sm">
              <template v-for="row in bugRows" :key="row.label">
                <dt class="text-muted">{{ row.label }}</dt>
                <dd class="break-words">
                  <a v-if="row.href" :href="row.href" target="_blank" rel="noopener noreferrer"
                    class="text-accent hover:underline">{{ row.value }}</a>
                  <template v-else>{{ row.value }}</template>
                </dd>
              </template>
            </dl>
            <div v-for="blk in bugTexts" :key="blk.label" class="mt-3">
              <div class="text-xs text-muted">{{ blk.label }}</div>
              <div class="text-sm whitespace-pre-wrap break-words">{{ blk.value }}</div>
            </div>
          </div>

          <!-- Assignees -->
          <div class="mt-5">
            <div class="text-xs text-muted mb-1">Assignees</div>
            <div class="flex flex-wrap items-center gap-1.5">
              <span v-for="a in task.assignees" :key="a" class="flex items-center gap-1 pill text-xs pl-2 pr-1 py-0.5">
                {{ a.replace(/@.*/, '') }}
                <button v-if="canWrite" @click="unassign(a)" class="hover:opacity-70">x</button>
              </span>
              <select v-if="canWrite" @change="assign($event)" class="text-xs border border-app bg-surface-2 text-app rounded-md px-1.5 py-1">
                <option value="">+ assign</option>
                <option v-for="u in assignable" :key="u.name" :value="u.name">{{ u.full_name || u.name }}</option>
              </select>
            </div>
          </div>

          <!-- Watchers: get update emails without being assigned -->
          <div class="mt-5">
            <div class="text-xs text-muted mb-1">Watchers <span class="opacity-70">(get update emails)</span></div>
            <div class="flex flex-wrap items-center gap-1.5">
              <span v-for="w in task.watchers" :key="w" class="flex items-center gap-1 pill text-xs pl-2 pr-1 py-0.5">
                {{ w.replace(/@.*/, '') }}
                <button v-if="canWrite" @click="removeWatcher(w)" class="hover:opacity-70">x</button>
              </span>
              <select v-if="canWrite" @change="addWatcher($event)" class="text-xs border border-app bg-surface-2 text-app rounded-md px-1.5 py-1">
                <option value="">+ watch</option>
                <option v-for="u in watchable.filter(u => !task.watchers.includes(u.name))" :key="u.name" :value="u.name">{{ u.full_name || u.name }}</option>
              </select>
            </div>
          </div>

          <!-- Time tracked -->
          <div class="mt-5">
            <div class="text-xs text-muted mb-1.5 flex items-center justify-between">
              <span>Time tracked</span>
              <span class="mono text-app">{{ timeTotal.toFixed(2) }} h</span>
            </div>
            <div v-for="e in timeEntries" :key="e.name" class="flex items-center gap-2 py-0.5 text-xs">
              <span class="text-faint w-20">{{ e.date }}</span>
              <span class="mono">{{ Number(e.hours).toFixed(2) }} h</span>
              <span class="text-muted truncate flex-1">{{ e.description || '' }}</span>
            </div>
            <div v-if="!timeEntries.length" class="text-[11px] text-faint py-1">No time tracked yet.</div>
            <div class="text-[11px] text-faint mt-1.5 leading-snug">
              Hours are measured in <b>Super Productivity</b> and synced automatically — they can't be typed in by hand.
            </div>
          </div>

          <!-- Attachments -->
          <div class="mt-5">
            <div class="text-xs text-muted mb-1.5 flex items-center justify-between">
              <span>Attachments</span>
              <label v-if="canWrite" class="btn cursor-pointer">
                <input type="file" class="hidden" @change="uploadFile" :disabled="uploading" />
                {{ uploading ? 'Uploading…' : 'Attach' }}
              </label>
            </div>
            <div v-for="f in attachments" :key="f.name" class="flex items-center gap-2 py-0.5 text-sm">
              <Paperclip class="w-3.5 h-3.5 text-faint shrink-0" />
              <a :href="f.file_url" target="_blank" class="truncate flex-1 hover:underline" style="color:var(--accent)">{{ f.file_name }}</a>
              <span class="text-[10px] text-faint">{{ fmtSize(f.file_size) }}</span>
              <button v-if="canWrite" class="text-faint hover:text-app" @click="removeAttachment(f.name)"><X class="w-3 h-3" /></button>
            </div>
            <div v-if="!attachments.length" class="text-xs text-faint py-1">No files attached.</div>
          </div>

          <!-- Parent -->
          <div v-if="task.parent" class="mt-4 text-xs">
            <span class="text-muted">Parent: </span>
            <span class="mono text-accent">{{ task.parent.issue_key }}</span>
            <span class="text-muted"> · {{ task.parent.subject }}</span>
          </div>

          <!-- Sub-tasks -->
          <div class="mt-5">
            <div class="text-xs text-muted mb-1.5 flex items-center justify-between">
              <span>Sub-tasks</span>
              <span v-if="task.subtasks.length" class="text-faint">{{ doneSubs }}/{{ task.subtasks.length }} done</span>
            </div>
            <div v-if="task.subtasks.length" class="h-1 rounded-full bg-surface-2 mb-2 overflow-hidden">
              <div class="h-full rounded-full" :style="{ width: subPct + '%', background: 'var(--term-green)' }" />
            </div>
            <div v-for="s in task.subtasks" :key="s.name" class="flex items-center gap-2 py-1 cursor-pointer group" @click="$emit('open', s.name)">
              <span class="mono text-[10px] text-faint">{{ s.issue_key }}</span>
              <span class="text-sm flex-1 truncate" :class="s.status === 'Completed' ? 'line-through text-muted' : ''">{{ s.subject }}</span>
              <StatusPill :value="s.status" />
            </div>
            <div v-if="canWrite" class="flex gap-2 mt-1.5">
              <input v-model="newSub" @keyup.enter="addSub" placeholder="Add sub-task…" class="field flex-1" />
              <button class="btn" @click="addSub">Add</button>
            </div>
          </div>

          <!-- Dependencies -->
          <div class="mt-5">
            <div class="text-xs text-muted mb-1.5">Blocked by</div>
            <div v-for="b in task.blocked_by" :key="b.dep" class="flex items-center gap-2 py-1">
              <span class="mono text-[10px] text-faint">{{ b.issue_key }}</span>
              <span class="text-sm flex-1 truncate">{{ b.subject }}</span>
              <StatusPill :value="b.status" />
              <button v-if="canWrite" class="text-faint hover:text-app" @click="removeDep(b.dep)"><X class="w-3 h-3" /></button>
            </div>
            <div v-if="canWrite" class="relative mt-1.5">
              <input v-model="depQ" @input="searchDeps" placeholder="Add a blocker (search tasks)…" class="field w-full" />
              <div v-if="depResults.length" class="absolute z-10 left-0 right-0 mt-1 rounded-md border border-app bg-surface shadow-app max-h-44 overflow-y-auto">
                <button v-for="r in depResults" :key="r.name" class="w-full text-left px-2.5 py-1.5 hover-app text-sm flex items-center gap-2" @click="addDep(r)">
                  <span class="mono text-[10px] text-faint">{{ r.issue_key }}</span><span class="truncate">{{ r.subject }}</span>
                </button>
              </div>
            </div>
          </div>

          <!-- Checklist -->
          <div class="mt-5">
            <div class="text-xs text-muted mb-1">Checklist</div>
            <div v-for="c in task.checklist" :key="c.name" class="flex items-center gap-2 py-0.5">
              <input type="checkbox" :checked="c.is_done" :disabled="!canWrite" @change="toggleCheck(c)" />
              <span :class="c.is_done ? 'line-through text-muted' : ''" class="text-sm">{{ c.item }}</span>
            </div>
            <div v-if="canWrite" class="flex gap-2 mt-1">
              <input v-model="newCheck" @keyup.enter="addCheck" placeholder="Add item..." class="field flex-1" />
              <button class="btn" @click="addCheck">Add</button>
            </div>
          </div>

          <!-- Comments -->
          <div class="mt-5">
            <div class="text-xs text-muted mb-1">Comments</div>
            <div v-if="!task.comments.length && !task.can_comment" class="text-xs text-faint py-1">No comments.</div>
            <div v-for="c in task.comments" :key="c.name" class="text-sm border-l-2 border-app pl-2 py-1">
              <div class="text-app rt-content break-words" v-html="toHtml(c.comment_text)" />
              <div class="text-[10px] text-muted">{{ c.owner }}</div>
            </div>
            <div v-if="task.can_comment" class="flex gap-2 mt-1">
              <div class="flex-1 min-w-0" @keydown.ctrl.enter="postComment" @keydown.meta.enter="postComment">
                <RichText :key="`c-${task.name}-${commentKey}`" v-model="newComment" :task-name="task.name" compact
                  :upload-function="uploadComment"
                  placeholder="Write a comment — paste images straight in (Ctrl+Enter to send)" />
              </div>
              <button class="btn self-start" @click="postComment">Send</button>
            </div>
          </div>
        </div>
        <div v-else class="p-10 text-center text-muted">Loading...</div>
      </aside>
    </div>
  </transition>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { call } from 'frappe-ui'
import { toast } from '@/ui/toast'
import StatusPill from '@/ui/StatusPill.vue'
import RichText from '@/components/RichText.vue'
import { toHtml, isEmptyHtml } from '@/utils/richtext'
import { deskUrl } from '@/utils/desk'
import { commentImageUploader } from '@/utils/upload'
import X from '~icons/lucide/x'
import Paperclip from '~icons/lucide/paperclip'

const props = defineProps({ taskId: { type: String, default: null } })
const emit = defineEmits(['close', 'changed', 'open'])

const task = ref(null)

// Pulse Viewer is read-only: the server refuses writes, and here every control that
// would change something is hidden or locked. (`can_write` comes from the /pulse page.)
const canWrite = window.can_write !== false
const uploadComment = computed(() => commentImageUploader(task.value?.name))

const bugRows = computed(() => {
  const b = task.value?.bug || {}
  const record = b.ref_doctype ? (b.ref_name ? `${b.ref_doctype} ${b.ref_name}` : b.ref_doctype) : ''
  return [
    { label: 'Reported by', value: b.reported_by },
    { label: 'Environment', value: b.environment },
    { label: 'Module', value: b.module },
    { label: 'Page', value: b.page, href: deskUrl(b.page) },
    { label: 'Record', value: record },
    { label: 'App version', value: b.app_version },
  ].filter((r) => r.value)
})

const bugTexts = computed(() => {
  const b = task.value?.bug || {}
  return [
    { label: 'Steps to reproduce', value: b.steps },
    { label: 'Expected result', value: b.expected },
    { label: 'Actual result', value: b.actual },
  ].filter((r) => r.value)
})
const assignable = ref([])
const watchable = ref([])
const issueTypes = ref([])
const newCheck = ref('')
const newComment = ref('')
const commentKey = ref(0)
const newSub = ref('')
const depQ = ref('')
const depResults = ref([])
const timeEntries = ref([])
const attachments = ref([])
const uploading = ref(false)
const epics = ref([])
const releases = ref([])
const releaseApps = ref([])

// Apps from Pulse Settings, plus this task's own if it has since been removed from the list.
const appOptions = computed(() => {
  const cur = task.value?.pulse_release_app
  return cur && !releaseApps.value.includes(cur) ? [...releaseApps.value, cur] : releaseApps.value
})
// Existing release tags for the chosen app (a tag belongs to an app).
const releaseSuggestions = computed(() => {
  const app = task.value?.pulse_release_app || ''
  return [...new Set(releases.value.filter((r) => (r.app || '') === app).map((r) => r.release_name))]
})

const doneSubs = computed(() => (task.value?.subtasks || []).filter((s) => s.status === 'Completed').length)
const subPct = computed(() => task.value?.subtasks?.length ? Math.round((doneSubs.value / task.value.subtasks.length) * 100) : 0)
const timeTotal = computed(() => timeEntries.value.reduce((s, e) => s + Number(e.hours || 0), 0))

async function loadTime(id) {
  timeEntries.value = await call('pulse.api.time.get_task_time_detail', { task: id }).catch(() => [])
}
async function loadAttachments(id) {
  attachments.value = await call('pulse.api.spa.list_attachments', { task: id }).catch(() => [])
}
async function uploadFile(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file, file.name)
    fd.append('doctype', 'Task')
    fd.append('docname', props.taskId)
    fd.append('is_private', '1')
    const res = await fetch('/api/method/upload_file', {
      method: 'POST',
      headers: { 'X-Frappe-CSRF-Token': window.csrf_token || '' },
      body: fd,
    })
    if (!res.ok) throw new Error('HTTP ' + res.status)
    await loadAttachments(props.taskId)
    toast.success('File attached')
  } catch (err) { toast.error('Upload failed') }
  finally { uploading.value = false }
}
async function removeAttachment(name) {
  await call('pulse.api.spa.delete_attachment', { name }).catch(() => {})
  await loadAttachments(props.taskId)
}
function fmtSize(b) {
  if (!b) return ''
  if (b < 1024) return b + ' B'
  if (b < 1048576) return (b / 1024).toFixed(0) + ' KB'
  return (b / 1048576).toFixed(1) + ' MB'
}

watch(() => props.taskId, async (id) => {
  task.value = null
  if (!id) return
  const [t, users, types, watchers] = await Promise.all([
    call('pulse.api.spa.get_task', { task: id }),
    assignable.value.length ? Promise.resolve(assignable.value) : call('pulse.api.spa.get_assignable_users'),
    issueTypes.value.length ? Promise.resolve(issueTypes.value)
      : call('pulse.api.spa.get_task_types'),
    watchable.value.length ? Promise.resolve(watchable.value) : call('pulse.api.spa.get_watchable_users'),
  ])
  task.value = t
  assignable.value = users
  watchable.value = watchers
  issueTypes.value = types
  loadTime(id)
  loadAttachments(id)
  // epic choices are project-scoped; releases are free-text suggestions
  epics.value = await call('pulse.api.planning.epic_options', { project: t.project }).catch(() => [])
  releases.value = await call('pulse.api.planning.list_releases').catch(() => [])
  releaseApps.value = await call('pulse.api.spa.get_release_apps').catch(() => [])
})

async function save(field, value) {
  try {
    await call('pulse.api.spa.update_task', { task: props.taskId, [field]: value })
    toast.success('Saved')
    emit('changed')
  } catch (e) { toast.error('Could not save changes') }
}
async function assign(e) {
  const user = e.target.value
  e.target.value = ''
  if (!user) return
  try {
    const r = await call('pulse.api.spa.assign_task', { task: props.taskId, user })
    task.value.assignees = r.assignees
    toast.success(`Assigned ${user.split('@')[0]}`)
    emit('changed')
  } catch (e2) { toast.error(e2?.messages?.[0] || 'Assignment not allowed') }
}
async function unassign(user) {
  const r = await call('pulse.api.spa.unassign_task', { task: props.taskId, user })
  task.value.assignees = r.assignees
  emit('changed')
}
async function addWatcher(e) {
  const user = e.target.value
  e.target.value = ''
  if (!user) return
  try {
    const r = await call('pulse.api.spa.watch_task', { task: props.taskId, user })
    task.value.watchers = r.watchers
    toast.success(`${user.split('@')[0]} will get updates`)
  } catch (e2) { toast.error(e2?.messages?.[0] || 'Could not add watcher') }
}
async function removeWatcher(user) {
  const r = await call('pulse.api.spa.unwatch_task', { task: props.taskId, user })
  task.value.watchers = r.watchers
}
async function addCheck() {
  if (!newCheck.value) return
  const r = await call('pulse.api.spa.add_checklist_item', { task: props.taskId, item: newCheck.value })
  task.value.checklist.push(r)
  newCheck.value = ''
}
async function toggleCheck(c) {
  await call('pulse.api.spa.toggle_checklist_item', { name: c.name, is_done: c.is_done ? 0 : 1 })
  c.is_done = c.is_done ? 0 : 1
}
async function postComment() {
  if (isEmptyHtml(newComment.value)) return
  const r = await call('pulse.api.spa.add_comment', { task: props.taskId, text: newComment.value })
  task.value.comments.push(r)
  newComment.value = ''
  commentKey.value++
}
async function addSub() {
  if (!newSub.value.trim()) return
  const s = await call('pulse.api.spa.add_subtask', { parent: props.taskId, subject: newSub.value.trim() })
  task.value.subtasks.push(s)
  newSub.value = ''
  toast.success(`Sub-task ${s.issue_key} added`)
  emit('changed')
}
let depTimer
function searchDeps() {
  clearTimeout(depTimer)
  depTimer = setTimeout(async () => {
    if (!depQ.value.trim()) { depResults.value = []; return }
    depResults.value = await call('pulse.api.spa.search_tasks', { q: depQ.value.trim(), exclude: props.taskId }).catch(() => [])
  }, 220)
}
async function addDep(r) {
  depQ.value = ''; depResults.value = []
  await call('pulse.api.spa.add_dependency', { task: props.taskId, depends_on: r.name })
  task.value.blocked_by.push({ dep: 'new', task: r.name, issue_key: r.issue_key, subject: r.subject, status: '' })
  toast.success(`Now blocked by ${r.issue_key}`)
  emit('changed')
}
async function removeDep(dep) {
  await call('pulse.api.spa.remove_dependency', { name: dep })
  task.value.blocked_by = task.value.blocked_by.filter((b) => b.dep !== dep)
}
</script>

<style scoped>
.field { width: 100%; margin-top: 0.125rem; font-size: 0.875rem; border: 1px solid var(--border); border-radius: 0.375rem; padding: 0.25rem 0.5rem; outline: none; background: var(--surface-2); color: var(--text); }
.field:focus { border-color: var(--accent); }
.field:disabled, .field[readonly] { opacity: 0.8; cursor: default; border-color: transparent; background: transparent; padding-left: 0; }
.field:disabled { appearance: none; }
.btn { font-size: 0.8125rem; padding: 0.35rem 0.85rem; border-radius: 999px; background: var(--accent); color: var(--on-accent); font-weight: 600; }
.btn:hover { filter: brightness(1.06); }
.slide-enter-active, .slide-leave-active { transition: opacity 0.15s; }
.slide-enter-from, .slide-leave-to { opacity: 0; }
</style>
