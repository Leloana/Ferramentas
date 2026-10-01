// Foto de perfil dos cantores (players/<apelido>/avatar.jpg no servidor).
// `version` vem de /api/players (campo avatar): muda a cada foto nova, então a
// URL com ?v= pode ficar no cache do navegador. Sem foto: a inicial do apelido.

export function avatarUrl(name, version) {
    return `/api/players/${encodeURIComponent(name)}/avatar?v=${version}`;
}

function initial(name) {
    const span = document.createElement('span');
    span.className = 'avatar avatar--initial';
    span.textContent = (String(name || '?').trim()[0] || '?').toUpperCase();
    return span;
}

// Elemento da foto (ou da inicial); `cls` acrescenta o tamanho de cada lugar.
export function avatarNode(name, version, cls) {
    let node;
    if (version) {
        node = document.createElement('img');
        node.className = 'avatar';
        node.src = avatarUrl(name, version);
        node.alt = '';
        node.loading = 'lazy';
        node.addEventListener('error', () => {
            const fallback = initial(name);
            if (cls) fallback.classList.add(cls);
            node.replaceWith(fallback);
        });
    } else {
        node = initial(name);
    }
    if (cls) node.classList.add(cls);
    return node;
}

export async function fetchAvatarVersion(name) {
    try {
        const resp = await fetch(`/api/players/${encodeURIComponent(name)}/avatar-version`);
        return resp.ok ? (await resp.json()).avatar : null;
    } catch (e) {
        return null;
    }
}

export async function uploadAvatar(name, file) {
    const form = new FormData();
    form.append('photo', file);
    const resp = await fetch(`/api/players/${encodeURIComponent(name)}/avatar`, { method: 'POST', body: form });
    if (!resp.ok) {
        let detail = 'Não deu para salvar a foto';
        try { detail = (await resp.json()).detail || detail; } catch (e) { /* sem corpo */ }
        throw new Error(detail);
    }
    return (await resp.json()).avatar;
}

export async function removeAvatar(name) {
    await fetch(`/api/players/${encodeURIComponent(name)}/avatar`, { method: 'DELETE' });
}
