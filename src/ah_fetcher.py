import asyncio
import aiohttp
import json
import time
from pathlib import Path
from src import data_manager
import config


class AsyncCoflnetFetcher:
    def __init__(
        self,
        tokens: list[str],
        dm: data_manager.Data,
        rate_limit_per_second: float = 2.5,
    ):
        self.tokens = [tokens] if isinstance(tokens, str) else tokens
        self.token_idx = 0
        self.dm = dm
        self.delay = 1.0 / max(rate_limit_per_second, 0.1)
        self.semaphore = asyncio.Semaphore(2)

    def get_token(self) -> str:
        if not self.tokens:
            return ""
        tok = self.tokens[self.token_idx % len(self.tokens)]
        self.token_idx += 1
        return tok

    async def fetch_item(
        self, session: aiohttp.ClientSession, itemId: str
    ) -> tuple[str, bool]:
        cache_path = self.dm.AH_DIR / f"{itemId}.json"

        # Если файл скачан меньше 6 часов назад — пропускаем
        if cache_path.is_file() and not self.dm.isCacheExpired(
            cache_path, cacheDuration=6
        ):
            return itemId, False

        url = f"https://sky.coflnet.com/api/item/price/{itemId}"
        params = {"Clean": "yes"}

        retries = 3
        while retries > 0:
            token = self.get_token()
            headers = {"Authorization": f"Bearer {token}"} if token else {}

            async with self.semaphore:
                try:
                    await asyncio.sleep(self.delay)
                    async with session.get(
                        url, headers=headers, params=params, timeout=10
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            self.dm.saveJson(data or {}, cache_path)
                            return itemId, True

                        elif resp.status == 429:
                            print(f"\n⚠️ [Лимит 429] Пауза 6 сек на {itemId}...")
                            await asyncio.sleep(6)
                            retries -= 1

                        elif resp.status == 404:
                            self.dm.saveJson(
                                {"volume": 0, "median": 0, "notFound": True},
                                cache_path,
                            )
                            return itemId, True
                        else:
                            retries -= 1

                except Exception:
                    retries -= 1
                    await asyncio.sleep(1)

        return itemId, True

    async def run(self, items_list: list[str]):
        total = len(items_list)
        print("=" * 65)
        print(f"🚀 СТАРТ СИНХРОНИЗАЦИИ ЦЕН COFLNET")
        print(f"📦 Предметов в очереди: {total} шт.")
        print("=" * 65)

        start_time = time.time()
        downloaded = 0
        from_cache = 0

        connector = aiohttp.TCPConnector(limit=5)
        async with aiohttp.ClientSession(connector=connector) as session:
            for idx, item in enumerate(items_list, 1):
                item_id, was_net = await self.fetch_item(session, item)

                if was_net:
                    downloaded += 1
                else:
                    from_cache += 1

                # Прогресс в консоль
                if idx % 15 == 0 or idx == total or was_net:
                    elapsed = time.time() - start_time
                    speed = downloaded / max(elapsed, 0.001)
                    remaining = total - idx
                    eta_min = (remaining / speed) / 60.0 if speed > 0 else 0
                    percent = (idx / total) * 100

                    print(
                        f"\r⏳ [{idx:>4}/{total}] ({percent:>5.1f}%) | "
                        f"С диска: {from_cache:<4} | Скачано: {downloaded:<4} | "
                        f"Осталось: {eta_min:.1f} мин | {item[:20]:<20}",
                        end="",
                        flush=True,
                    )

        total_time = time.time() - start_time
        print("\n\n" + "=" * 65)
        print(f"🎉 ГОТОВО! Всё скачано за {total_time / 60:.1f} мин.")
        print(f"📁 Новых: {downloaded} | Взято из кэша: {from_cache}")
        print("=" * 65)
