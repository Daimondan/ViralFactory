/* ViralFactory — busy.js
 * Shared client-side helper for F1 busy states + idempotency.
 * Included by every template that has action buttons.
 *
 * Usage:
 *   busyAction(btn, url, options) — wraps a fetch POST with busy state.
 *     - Disables the triggering button, swaps label to working state.
 *     - On completion or error, restores the button.
 *     - If the server returns 409 (already running), shows "already working on it."
 *     - Long-running actions show an inline status line near the affected content.
 *
 *   busyBtn(btn, label) — manually set a button to busy state.
 *   unbusyBtn(btn, originalLabel) — restore a button.
 */

// ── Button state helpers ─────────────────────────────────────

function busyBtn(btn, label) {
    if (!btn) return;
    btn.dataset.busy = '1';
    btn.dataset.originalLabel = btn.textContent;
    btn.disabled = true;
    btn.textContent = label || 'Working…';
    btn.style.opacity = '0.6';
    btn.style.cursor = 'wait';
}

function unbusyBtn(btn) {
    if (!btn) return;
    btn.disabled = false;
    btn.dataset.busy = '';
    if (btn.dataset.originalLabel) {
        btn.textContent = btn.dataset.originalLabel;
        delete btn.dataset.originalLabel;
    }
    btn.style.opacity = '';
    btn.style.cursor = '';
}

// ── Status line helper ───────────────────────────────────────

function setStatusLine(elem, text, isError) {
    if (!elem) return;
    if (!elem.id) {
        elem.id = 'status-' + Math.random().toString(36).slice(2, 9);
    }
    let line = document.getElementById(elem.id + '-status');
    if (!line) {
        line = document.createElement('div');
        line.id = elem.id + '-status';
        line.style.fontSize = '0.82rem';
        line.style.marginTop = '6px';
        elem.appendChild(line);
    }
    line.textContent = text;
    line.style.color = isError ? '#cc4a4a' : '#5b9fd6';
}

// ── Main action wrapper ─────────────────────────────────────

function busyAction(btn, url, options) {
    options = options || {};
    var method = options.method || 'POST';
    var body = options.body || '{}';
    var busyLabel = options.busyLabel || 'Working…';
    var statusElem = options.statusElem || null;
    var onSuccess = options.onSuccess || function(data) { window.location.reload(); };
    var onError = options.onError || function(msg) { vfToastError('Something went wrong', msg); };
    var reloadOnSuccess = options.reloadOnSuccess !== false;  // default true

    // If button is already busy, do nothing
    if (btn && btn.dataset.busy === '1') return;

    busyBtn(btn, busyLabel);
    if (statusElem) setStatusLine(statusElem, busyLabel, false);

    fetch(url, {
        method: method,
        headers: {'Content-Type': 'application/json'},
        body: body,
    }).then(function(r) {
        if (r.status === 409) {
            // Job already running — don't fire again
            return r.json().then(function(data) {
                var msg = data.message || 'Already working on it.';
                if (statusElem) setStatusLine(statusElem, msg, false);
                unbusyBtn(btn);
            });
        }
        return r.json().then(function(data) {
            if (data.status === 'ok' || data.status === 'already_exists') {
                unbusyBtn(btn);
                if (data.message && statusElem) {
                    setStatusLine(statusElem, data.message, false);
                }
                if (reloadOnSuccess) {
                    window.location.reload();
                } else if (onSuccess) {
                    onSuccess(data);
                }
            } else {
                unbusyBtn(btn);
                var msg = data.error || 'unknown error';
                if (statusElem) setStatusLine(statusElem, msg, true);
                onError(msg);
            }
        });
    }).catch(function(err) {
        unbusyBtn(btn);
        var msg = 'Network error: ' + err;
        if (statusElem) setStatusLine(statusElem, msg, true);
        onError(msg);
    });
}
