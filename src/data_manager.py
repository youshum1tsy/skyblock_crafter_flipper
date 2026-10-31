import io, zipfile, os, shutil, json, pathlib
from datetime import datetime, timedelta


class RecipeManager:
    """
    Отвечает за парсинг, нормализацию рецептов (Crafting & Forge),
    расчёт себестоимости с учётом цен Базара / AH и поиск выгодных крафтов.
    """

    def __init__(self, data: "Data"):
        self.data = data

    @staticmethod
    def parseIngredient(itemStr: str) -> tuple[str, int]:
        """
        Разбирает строку вида 'ITEM_ID:COUNT' на кортеж (itemId, count).
        Корректно обрабатывает пустые строки и отсутствие количества.
        """
        if not itemStr or not isinstance(itemStr, str):
            return "", 0

        if ":" in itemStr:
            parts = itemStr.rsplit(":", 1)
            itemId = parts[0]
            try:
                count = int(parts[1])
            except ValueError:
                count = 1
            return itemId, count

        return itemStr, 1

    def loadRecipes(self) -> None:
        """
        Загружает все JSON-файлы рецептов из RECIPES_DIR и нормализует их
        в единую структуру внутри self.data.itemRecipesDb.
        """
        self.data.itemRecipesDb.clear()

        for filePath in self.data.RECIPES_DIR.iterdir():
            if not filePath.is_file() or filePath.suffix != ".json":
                continue

            try:
                data = json.loads(filePath.read_text(encoding="utf-8"))
            except Exception:
                continue

            itemName = filePath.stem
            normalizedRecipes = []

            # --- 1. Обычный крафт на верстаке: "recipe" ---
            if "recipe" in data and isinstance(data["recipe"], dict):
                rData = data["recipe"]
                outputCount = rData.get("count", 1)
                inputs = {}

                for slot, val in rData.items():
                    if slot == "count" or not val or not isinstance(val, str):
                        continue
                    ingId, count = self.parseIngredient(val)
                    if ingId:
                        inputs[ingId] = inputs.get(ingId, 0) + count

                if inputs:
                    normalizedRecipes.append(
                        {
                            "outputId": itemName,
                            "outputCount": outputCount,
                            "type": "crafting",
                            "duration": 0,
                            "inputs": inputs,
                        }
                    )

            # --- 2. Список "recipes" (Forge или несколько рецептов верстака) ---
            if "recipes" in data and isinstance(data["recipes"], list):
                for r in data["recipes"]:
                    if not isinstance(r, dict):
                        continue

                    rType = r.get("type", "crafting")
                    outputId = r.get("overrideOutputId", itemName)
                    outputCount = r.get("count", 1)
                    duration = r.get("duration", 0)
                    inputs = {}

                    # Если Forge: ингредиенты лежат в списке "inputs"
                    if rType == "forge":
                        for rawItem in r.get("inputs", []):
                            ingId, count = self.parseIngredient(rawItem)
                            if ingId:
                                inputs[ingId] = inputs.get(ingId, 0) + count

                    # Если верстак внутри массива "recipes" (A1..C3)
                    elif rType == "crafting":
                        for slot, val in r.items():
                            if (
                                slot in ("type", "count", "overrideOutputId")
                                or not val
                                or not isinstance(val, str)
                            ):
                                continue
                            ingId, count = self.parseIngredient(val)
                            if ingId:
                                inputs[ingId] = inputs.get(ingId, 0) + count

                    if inputs:
                        normalizedRecipes.append(
                            {
                                "outputId": outputId,
                                "outputCount": outputCount,
                                "type": rType,
                                "duration": duration,
                                "inputs": inputs,
                            }
                        )

            if normalizedRecipes:
                self.data.itemRecipesDb[itemName] = normalizedRecipes

    def getItemPrice(self, itemId: str, preferOrder: bool = False) -> float | None:
        """
        Ищет цену предмета:
        1. На Базаре (pricesBz)
        2. На Аукционе (pricesAh, Lowest BIN / Median)
        """
        # 1. Поиск по Базару
        if itemId in self.data.itemBzPricesDb:
            val = self.data.itemBzPricesDb[itemId]
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, dict):
                qs = val.get("quick_status", val)
                priceKey = "sellPrice" if preferOrder else "buyPrice"
                price = (
                    qs.get(priceKey)
                    or qs.get("buyPrice")
                    or qs.get("buy_price")
                    or qs.get("price")
                )
                if price is not None and price > 0:
                    return float(price)

        # 2. Поиск по Аукциону (AH)
        if itemId in self.data.itemAhPricesDb:
            val = self.data.itemAhPricesDb[itemId]
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, dict):
                min_p = val.get("min", 0)
                # Игнорируем ставки меньше 1000 монет, чтобы не брать аукционы за 10 монет
                price = (
                    val.get("buy")
                    or val.get("lowest_bin")
                    or val.get("lowestBin")
                    or val.get("median")
                    or (min_p if min_p > 1000 else None)
                    or val.get("price")
                )
                if price is not None and price > 0:
                    return float(price)

        return None

    def calculateCraftCost(
        self, recipe: dict, preferOrder: bool = False
    ) -> float | None:
        """
        Считает себестоимость одной штуки готового предмета по рецепту.
        Возвращает None, если цена хотя бы одного ингредиента неизвестна.
        """
        totalCost = 0.0

        for ingId, count in recipe.get("inputs", {}).items():
            price = self.getItemPrice(ingId, preferOrder=preferOrder)
            if price is None or price <= 0:
                return None

            totalCost += price * count

        outputCount = recipe.get("outputCount", 1)
        return totalCost / max(outputCount, 1)

    def findBestFlips(
        self,
        bzTax: float = 0.0125,
        ahTax: float = 0.02,
        preferOrder: bool = False,
    ) -> list[dict]:
        """
        Рассчитывает прибыль для всех загруженных рецептов (Crafting + Forge).
        Сортирует по чистой прибыли.
        """
        flips = []

        for itemName, recipes in self.data.itemRecipesDb.items():
            for recipe in recipes:
                craftCost = self.calculateCraftCost(recipe, preferOrder=preferOrder)
                if craftCost is None:
                    continue

                targetId = recipe["outputId"]

                # Проверяем, не заблокирован ли предмет для продажи
                if targetId in self.data.notAuctionableIds:
                    continue

                sellPrice = self.getItemPrice(targetId)
                if not sellPrice or sellPrice <= craftCost:
                    continue

                # Выбираем налог (Базар или AH)
                taxRate = bzTax if targetId in self.data.itemBzPricesDb else ahTax
                netRevenue = sellPrice * (1.0 - taxRate)
                profit = netRevenue - craftCost

                if profit <= 0:
                    continue

                roi = (profit / craftCost) * 100.0
                duration = recipe.get("duration", 0)
                profitPerHour = (
                    round((profit / duration) * 3600, 1) if duration > 0 else "Instant"
                )

                flips.append(
                    {
                        "itemId": targetId,
                        "type": recipe.get("type", "crafting"),
                        "craftCost": round(craftCost, 1),
                        "sellPrice": round(sellPrice, 1),
                        "profit": round(profit, 1),
                        "roiPercent": round(roi, 2),
                        "durationSec": duration,
                        "profitPerHour": profitPerHour,
                    }
                )

        flips.sort(key=lambda x: x["profit"], reverse=True)
        return flips


class Data:
    BASE_DIR = pathlib.Path("data")
    ETAG_PATH = BASE_DIR / "eTag.txt"

    RECIPES_DIR = BASE_DIR / "itemsRecipes"
    RECIPES_TEMP_DIR = BASE_DIR / "itemsRecipes_temp"

    AH_DIR = BASE_DIR / "pricesAh"
    BZ_DIR = BASE_DIR / "pricesBz"
    REGISTRY_DIR = BASE_DIR / "itemsRegistry"

    BZ_FILE_PATH = BZ_DIR / "bz.json"
    REGISTRY_FILE_PATH = REGISTRY_DIR / "registry.json"

    def __init__(self):
        self.itemRecipesDb = {}
        self.itemAhPricesDb = {}
        self.itemBzPricesDb = {}
        self.itemRegistryDb = {}
        self.notAuctionableIds = set()
        self.oldETag = self.readETag()

        # Инициализируем менеджер рецептов
        self.recipeManager = RecipeManager(self)

    def readETag(self) -> str:
        if self.ETAG_PATH.is_file():
            return self.ETAG_PATH.read_text(encoding="utf-8")
        return ""

    def writeETag(self, newETag: str) -> None:
        self.ETAG_PATH.write_text(newETag, encoding="utf-8")

    def unpackRecipes(self, itemsBytes: bytes) -> None:
        itemsBuff = io.BytesIO(itemsBytes)

        if self.RECIPES_TEMP_DIR.is_dir():
            shutil.rmtree(str(self.RECIPES_TEMP_DIR))
        self.RECIPES_TEMP_DIR.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(itemsBuff) as itemsZip:
            allZipPath = itemsZip.namelist()
            for path in allZipPath:
                if "/items/" in path and not (path.endswith("/")):
                    itemsFileName = path.split("/items/")[1]
                    filepath = self.RECIPES_TEMP_DIR / itemsFileName
                    filepath.write_bytes(itemsZip.read(path))

        if self.RECIPES_DIR.is_dir():
            shutil.rmtree(str(self.RECIPES_DIR))
        self.RECIPES_TEMP_DIR.rename(self.RECIPES_DIR)

    def loadRecipes(self) -> None:
        """Делегирует загрузку и нормализацию рецептов в RecipeManager."""
        self.recipeManager.loadRecipes()

    def isCacheExpired(
        self,
        filePath: pathlib.Path,
        cacheDuration: timedelta | int = timedelta(hours=1),
    ) -> bool:
        if isinstance(cacheDuration, int):
            cacheDuration = timedelta(hours=cacheDuration)

        if not filePath.is_file():
            return True
        mtime = filePath.stat().st_mtime
        fileDate = datetime.fromtimestamp(mtime)
        return datetime.now() - fileDate > cacheDuration

    def saveJson(self, dataDict: dict, filePath: pathlib.Path):
        filePath.parent.mkdir(parents=True, exist_ok=True)
        filePath.write_text(json.dumps(dataDict, indent=2), encoding="utf-8")

    def loadJson(self, filePath: pathlib.Path) -> dict:
        if not filePath.is_file():
            return {}
        return json.loads(filePath.read_text(encoding="utf-8"))

    def filterRegistry(self):
        itemList = self.itemRegistryDb.get("items", [])
        for item in itemList:
            if (
                (item.get("soulbound") is not None)
                or (item.get("can_auction") == False)
                or (item.get("can_trade") == False)
                or (item.get("category") == "SACK")
                or ("_GENERATOR_" in item.get("id", ""))
            ):
                self.notAuctionableIds.add(item.get("id"))


def getAhCraftableWhitelist(self) -> list[str]:
    """
    Сканирует локальную базу рецептов и возвращает список ID предметов,
    которые:
    1. Имеют реальный рецепт (Верстак или Кузница).
    2. НЕ продаются на Базаре (значит, торгуются на AH).
    3. НЕ являются Soulbound / квестовыми / непередаваемыми.
    """
    bzProducts = set(self.data.itemBzPricesDb.get("products", {}).keys())
    soulboundIds = self.data.notAuctionableIds

    ahCandidates = set()

    for itemName, recipes in self.data.itemRecipesDb.items():
        for recipe in recipes:
            targetId = recipe.get("outputId", itemName)

            # 1. Отсекаем всё, что продается на Базаре
            # (учитываем возможные префиксы типа INK_SACK:3)
            baseBzKey = targetId.replace("-", ":") if "-" in targetId else targetId
            if targetId in bzProducts or baseBzKey in bzProducts:
                continue

            # 2. Отсекаем Soulbound и непередаваемые предметы
            if targetId in soulboundIds or baseBzKey in soulboundIds:
                continue

            # 3. Проверяем, что в рецепте есть реальные ингредиенты
            inputs = recipe.get("inputs", {})
            if not inputs or len(inputs) == 0:
                continue

            # Если проверка пройдена — это наш целевой предмет для AH
            ahCandidates.add(targetId)

    sortedList = sorted(list(ahCandidates))

    # Сохраняем результат в файл для наглядности
    whitelistPath = self.data.BASE_DIR / "ah_craftable_whitelist.json"
    self.data.saveJson(
        {"totalCount": len(sortedList), "items": sortedList}, whitelistPath
    )

    return sortedList
