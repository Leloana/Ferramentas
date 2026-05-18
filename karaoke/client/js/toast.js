export function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    let iconSvg = '';
    if (type === 'success') {
        iconSvg = `<svg viewBox="0 0 24 24" width="20" height="20" stroke="var(--success)" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
    } else if (type === 'error') {
        iconSvg = `<svg viewBox="0 0 24 24" width="20" height="20" stroke="var(--error)" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" x2="12" y1="8" y2="12"></line><line x1="12" x2="12.01" y1="16" y2="16"></line></svg>`;
    } else if (type === 'warning') {
        iconSvg = `<svg viewBox="0 0 24 24" width="20" height="20" stroke="var(--warning)" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path><line x1="12" x2="12" y1="9" y2="13"></line><line x1="12" x2="12.01" y1="17" y2="17"></line></svg>`;
    } else {
        iconSvg = `<svg viewBox="0 0 24 24" width="20" height="20" stroke="var(--accent)" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" x2="12" y1="16" y2="12"></line><line x1="12" x2="12.01" y1="8" y2="8"></line></svg>`;
    }

    const iconDiv = document.createElement('div');
    iconDiv.className = 'toast-icon';
    iconDiv.innerHTML = iconSvg;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'toast-content';
    contentDiv.innerHTML = message;

    const closeBtn = document.createElement('button');
    closeBtn.className = 'toast-close';
    closeBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><line x1="18" x2="6" y1="6" y2="18"></line><line x1="6" x2="18" y1="6" y2="18"></line></svg>`;
    closeBtn.addEventListener('click', () => {
        toast.classList.add('fading-out');
        setTimeout(() => toast.remove(), 300);
    });

    toast.appendChild(iconDiv);
    toast.appendChild(contentDiv);
    toast.appendChild(closeBtn);

    container.appendChild(toast);

    setTimeout(() => {
        if (toast.parentElement) {
            toast.classList.add('fading-out');
            setTimeout(() => toast.remove(), 300);
        }
    }, 4700);
}
