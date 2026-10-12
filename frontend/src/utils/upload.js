// Image paste in comments goes through a Pulse endpoint rather than Frappe's upload_file,
// so a Pulse Viewer commenting on a task they raised can still add a screenshot.
export function commentImageUploader(task) {
  return async (file) => {
    const body = new FormData()
    body.append('file', file, file.name)
    body.append('task', task)
    const res = await fetch('/api/method/pulse.api.spa.upload_comment_image', {
      method: 'POST',
      headers: { 'X-Frappe-CSRF-Token': window.csrf_token || '', Accept: 'application/json' },
      body,
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok || !data.message) {
      let reason = 'Upload failed'
      try { reason = JSON.parse(JSON.parse(data._server_messages)[0]).message || reason } catch (e) {}
      throw new Error(reason)
    }
    return data.message
  }
}
