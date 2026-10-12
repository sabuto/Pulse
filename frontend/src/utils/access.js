// Pulse Viewer is read-only. The server refuses their writes; this just hides or locks
// the controls. `can_write` is put on the page by pulse/www/pulse.py.
export const canWrite = window.can_write !== false
