"""Leitura de campos do `meta.json` com fallback para layout antigo (flat).

O formato atual é aninhado: `meta.{title,artist,language}`, `audio.{...}`,
`lyrics.{...}`, `status.{...}`. Mas algumas pastas legadas têm o layout
plano (`title`, `artist` no topo). Este helper tenta o aninhado primeiro
e cai pro flat — usado tanto pelo `SongManager` quanto pelo
`reinstall_song`.
"""
from __future__ import annotations


def get_meta_field(meta: dict, section: str, key: str, default=None):
    """Retorna `meta[section][key]` se existir; senão `meta[key]`; senão `default`."""
    if isinstance(meta.get(section), dict):
        val = meta[section].get(key)
        if val is not None:
            return val
    return meta.get(key, default)
