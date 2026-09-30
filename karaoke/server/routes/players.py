"""Perfis dos cantores: lista (ranking) e perfil de um apelido."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Response

from players import list_profiles, load_profile, profile_detail, song_leaderboard
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


@router.get("/api/songs/{song_id}/leaderboard")
async def api_song_leaderboard(song_id: str, response: Response):
    set_no_cache(response)
    return {"leaderboard": await asyncio.to_thread(song_leaderboard, song_id, song_id)}
