"""Defense-in-depth for internal embedding callers (public RAG routes are off)."""

import aiohttp
import requests
from .gateway import connection, headers


async def async_embeddings(model, texts):
    url, _, _ = connection()
    async with aiohttp.ClientSession(trust_env=True, timeout=aiohttp.ClientTimeout(total=60)) as session:
        async with session.post(
            url + '/embeddings', headers=headers(), json={'model': model, 'input': texts}, allow_redirects=False
        ) as response:
            response.raise_for_status()
            data = await response.json()
    return [item['embedding'] for item in data['data']]


def sync_embeddings(model, texts):
    url, _, _ = connection()
    response = requests.post(
        url + '/embeddings', headers=headers(), json={'model': model, 'input': texts}, allow_redirects=False, timeout=60
    )
    response.raise_for_status()
    return [item['embedding'] for item in response.json()['data']]
