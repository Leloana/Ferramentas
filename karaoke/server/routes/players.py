"""Perfis dos cantores: lista (ranking) e perfil de um apelido."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse

from players import (AVATAR_MAX_UPLOAD_BYTES, avatar_path, avatar_version, delete_avatar, list_profiles,
                     load_profile, profile_detail, save_avatar, song_leaderboard)
from utils.http import set_no_cache

router = APIRouter()


@router.get("/api/players")
async def api_players(response: Response):
    set_no_cache(response)
    return {"players": await asyncio.to_thread(list_profiles)}


@router.get("/api/players/{name}")
async def api_player(name: str, response: Response):
    set_no_cache(response)
    profile = await asyncio.to_thread(load_profile, name)
    if not profile or not profile.get("songs_sung"):
        raise HTTPException(status_code=404, detail="Cantor sem partidas")
    return profile_detail(profile)


@router.get("/api/players/{name}/avatar")
async def api_player_avatar(name: str):
    path = avatar_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Sem foto")
    # a URL leva ?v=<versão>: a mesma URL é a mesma foto
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=31536000"})


@router.post("/api/players/{name}/avatar")
async def api_player_avatar_upload(name: str, photo: UploadFile = File(...)):
    data = await photo.read(AVATAR_MAX_UPLOAD_BYTES + 1)
    if len(data) > AVATAR_MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Foto grande demais")
    try:
        version = await asyncio.to_thread(save_avatar, name, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"avatar": version}


@router.delete("/api/players/{name}/avatar")
async def api_player_avatar_delete(name: str):
    await asyncio.to_thread(delete_avatar, name)
    return {"avatar": None}


@router.get("/api/players/{name}/avatar-version")
async def api_player_avatar_version(name: str, response: Response):
    """Versão da foto de quem ainda não cantou (o perfil dá 404 sem partidas)."""
    set_no_cache(response)
    return {"avatar": avatar_version(name)}


@router.get("/api/songs/{song_id}/leaderboard")
async def api_song_leaderboard(song_id: str, response: Response):
    set_no_cache(response)
    return {"leaderboard": await asyncio.to_thread(song_leaderboard, song_id, song_id)}
