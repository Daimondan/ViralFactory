/* ViralFactory — vf-ui.js
 * UI components ported from Astryx design patterns, implemented as
 * pure vanilla JS with no framework dependencies.
 *
 * Components:
 *   vfToast(type, title, message, options) — non-blocking toast notification
 *   vfSkeleton.show(container, count) — inject skeleton placeholder cards
 *   vfSkeleton.hide(container) — remove skeleton placeholders
 *
 * Design: Astryx visual language (Meta), ported to Flask/CSS stack per
 * charter rule "boring web tech: server-rendered Flask + minimal JS."
 */

// ── Toast Notifications ──────────────────────────────────────

var vfToastContainer = null;

function vfGetToastContainer() {
    if (!vfToastContainer || !document.body.contains(vfToastContainer)) {
        vfToastContainer = document.createElement('div');
        vfToastContainer.className = 'vf-toast-container';
        document.body.appendChild(vfToastContainer);
    }
    return vfToastContainer;
}

/**
 * Show a toast notification.
 * @param {string} type - 'success' | 'error' | 'info' | 'warning'
 * @param {string} title - Bold title line
 * @param {string} message - Body text (optional, can be empty)
 * @param {object} opts - { duration: ms (default 4000), sticky: bool (default false) }
 */
function vfToast(type, title, message, opts) {
    opts = opts || {};
    var duration = opts.duration !== undefined ? opts.duration : 4000;
    var sticky = opts.sticky || false;

    var container = vfGetToastContainer();
    var icons = { success: '✓', error: '✕', info: 'ℹ', warning: '⚠' };
    var icon = icons[type] || icons.info;

    var toast = document.createElement('div');
    toast.className = 'vf-toast vf-toast-' + type;

    var iconSpan = document.createElement('span');
    iconSpan.className = 'vf-toast-icon';
    iconSpan.textContent = icon;

    var body = document.createElement('div');
    body.className = 'vf-toast-body';
    var titleDiv = document.createElement('div');
    titleDiv.className = 'vf-toast-title';
    titleDiv.textContent = title;
    body.appendChild(titleDiv);
    if (message) {
        var msgDiv = document.createElement('div');
        msgDiv.textContent = message;
        body.appendChild(msgDiv);
    }

    var closeBtn = document.createElement('button');
    closeBtn.className = 'vf-toast-close';
    closeBtn.innerHTML = '&times;';
    closeBtn.setAttribute('aria-label', 'Dismiss');
    closeBtn.onclick = function() { dismissToast(toast); };

    toast.appendChild(iconSpan);
    toast.appendChild(body);
    toast.appendChild(closeBtn);
    container.appendChild(toast);

    if (!sticky && duration > 0) {
        setTimeout(function() { dismissToast(toast); }, duration);
    }
    return toast;
}

function dismissToast(toast) {
    if (!toast || toast.classList.contains('vf-toast-dismissing')) return;
    toast.classList.add('vf-toast-dismissing');
    setTimeout(function() {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 200);
}

// Convenience wrappers
function vfToastSuccess(title, message, opts) { return vfToast('success', title, message, opts); }
function vfToastError(title, message, opts) { return vfToast('error', title, message, opts); }
function vfToastInfo(title, message, opts) { return vfToast('info', title, message, opts); }
function vfToastWarning(title, message, opts) { return vfToast('warning', title, message, opts); }

// ── Skeleton Loaders ──────────────────────────────────────────

var vfSkeleton = {

    /**
     * Inject skeleton placeholder cards into a container.
     * @param {HTMLElement|string} container - DOM element or selector
     * @param {int} count - number of skeleton cards to show (default 3)
     */
    show: function(container, count) {
        if (typeof container === 'string') container = document.querySelector(container);
        if (!container) return;
        count = count || 3;

        // Save original content so it can be restored
        container.dataset.vfSkeletonOriginal = '1';
        container._vfSkeletonChildren = Array.prototype.slice.call(container.children);

        // Clear container
        while (container.firstChild) container.removeChild(container.firstChild);

        for (var i = 0; i < count; i++) {
            var card = document.createElement('div');
            card.className = 'vf-skeleton-card';
            card.innerHTML =
                '<div class="vf-skeleton-row">' +
                '  <span class="vf-skeleton vf-skeleton-avatar"></span>' +
                '  <div style="flex:1">' +
                '    <span class="vf-skeleton vf-skeleton-line short"></span>' +
                '  </div>' +
                '</div>' +
                '<span class="vf-skeleton vf-skeleton-line wide"></span>' +
                '<span class="vf-skeleton vf-skeleton-line wide"></span>' +
                '<span class="vf-skeleton vf-skeleton-line short"></span>';
            container.appendChild(card);
        }
    },

    /**
     * Remove skeleton placeholders and restore original content.
     * @param {HTMLElement|string} container - DOM element or selector
     */
    hide: function(container) {
        if (typeof container === 'string') container = document.querySelector(container);
        if (!container || !container.dataset.vfSkeletonOriginal) return;

        while (container.firstChild) container.removeChild(container.firstChild);

        if (container._vfSkeletonChildren) {
            for (var i = 0; i < container._vfSkeletonChildren.length; i++) {
                container.appendChild(container._vfSkeletonChildren[i]);
            }
            container._vfSkeletonChildren = null;
        }
        delete container.dataset.vfSkeletonOriginal;
    },

    /**
     * Create a single skeleton card element (for manual insertion).
     */
    card: function() {
        var card = document.createElement('div');
        card.className = 'vf-skeleton-card';
        card.innerHTML =
            '<div class="vf-skeleton-row">' +
            '  <span class="vf-skeleton vf-skeleton-avatar"></span>' +
            '  <div style="flex:1">' +
            '    <span class="vf-skeleton vf-skeleton-line short"></span>' +
            '  </div>' +
            '</div>' +
            '<span class="vf-skeleton vf-skeleton-line wide"></span>' +
            '<span class="vf-skeleton vf-skeleton-line wide"></span>' +
            '<span class="vf-skeleton vf-skeleton-line short"></span>';
        return card;
    }
};