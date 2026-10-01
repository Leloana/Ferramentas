// Origem que os celulares devem abrir (QR Codes de pareamento e de adicionar música).
//
// 1. Servidor atrás do túnel informa KARAOKE_PUBLIC_URL → usa ela.
// 2. TV aberta por localhost/IP → troca pelo IP da rede local (modo Wi-Fi).
// 3. TV aberta por um domínio → mantém o domínio. Trocar pelo IP aqui mandaria
//    o celular para https://192.168.x.x na porta 443, onde não há nada.
const IPV4_RE = /^\d{1,3}(\.\d{1,3}){3}$/;

function isLocalHostname(hostname) {
    return hostname === 'localhost' || IPV4_RE.test(hostname);
}

export async function resolvePublicOrigin() {
    const { protocol, host, hostname, port } = window.location;
    let info = null;
    try {
        const res = await fetch('/api/get-ip');
        if (res.ok) info = await res.json();
    } catch (e) {
        console.warn('Nao foi possivel consultar /api/get-ip, usando o host do navegador:', e);
    }

    if (info && info.public_url) return info.public_url.replace(/\/+$/, '');
    if (isLocalHostname(hostname) && info && info.ip && info.ip !== '127.0.0.1') {
        return `${protocol}//${info.ip}${port ? `:${port}` : ''}`;
    }
    return `${protocol}//${host}`;
}
