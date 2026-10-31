import asyncio
from src import data_manager, ah_fetcher
import config

dm = data_manager.Data()

# Читаем белый список, который сгенерировал audit.py
whitelist_file = dm.BASE_DIR / "ah_craftable_whitelist.json"
if not whitelist_file.is_file():
    print("❌ Файл ah_craftable_whitelist.json не найден! Сначала запусти audit.py")
    exit()

whitelist_data = dm.loadJson(whitelist_file)
items_to_fetch = whitelist_data.get("items", [])

# Запускаем загрузчик
token = getattr(config, "skyCoflApiToken", "")
fetcher = ah_fetcher.AsyncCoflnetFetcher(
    tokens=[token], dm=dm, rate_limit_per_second=2.5
)

asyncio.run(fetcher.run(items_to_fetch))
