import math
import time
from pathlib import Path
from src import data_manager, calculator, api, utils
import config


def getAhData(findItem: str, dataManager: data_manager.Data) -> dict:
    """Мгновенно берет цену предмета из локального кэша AH."""
    if findItem in dataManager.itemAhPricesDb:
        return dataManager.itemAhPricesDb[findItem]

    ahFilePath = dataManager.AH_DIR / f"{findItem}.json"
    if ahFilePath.is_file():
        priceData = dataManager.loadJson(ahFilePath)
        dataManager.itemAhPricesDb[findItem] = priceData or {}
        return dataManager.itemAhPricesDb[findItem]

    return {}


def getBzData(client, dataManager: data_manager.Data):
    if dataManager.isCacheExpired(dataManager.BZ_FILE_PATH):
        dataManager.itemBzPricesDb = client.getBazaarPrices()
        dataManager.saveJson(
            dataManager.itemBzPricesDb,
            dataManager.BZ_FILE_PATH,
        )
        print("BZ FROM API")
    else:
        dataManager.itemBzPricesDb = dataManager.loadJson(dataManager.BZ_FILE_PATH)
        print("BZ FROM FILE")


def getRegistryData(client, dataManager: data_manager.Data):
    if dataManager.isCacheExpired(dataManager.REGISTRY_FILE_PATH, cacheDuration=24):
        dataManager.itemRegistryDb = client.getSkyblockItems()
        dataManager.saveJson(dataManager.itemRegistryDb, dataManager.REGISTRY_FILE_PATH)
        dataManager.filterRegistry()
        print("SOULBOUND FROM API")
    else:
        dataManager.itemRegistryDb = dataManager.loadJson(
            dataManager.REGISTRY_FILE_PATH
        )
        dataManager.filterRegistry()
        print("SOULBOUND FROM FILE")


def getRecipeData(itemsBytes, newETag, dataManager: data_manager.Data):
    if itemsBytes is None and dataManager.RECIPES_DIR.is_dir():
        dataManager.loadRecipes()
        print("RECIPE FROM FILE")
    else:
        if itemsBytes is None:
            itemsBytes, newETag = api.fetchItems(eTag="")
        print("RECIPE FROM API")
        dataManager.unpackRecipes(itemsBytes)
        dataManager.writeETag(newETag)
        dataManager.loadRecipes()


# 1. Инициализация и загрузка баз
client = api.HypixelClient(apiKey=config.hypixelApiToken)
dataManager = data_manager.Data()
itemsBytes, newETag = api.fetchItems(dataManager.oldETag)

getRecipeData(itemsBytes, newETag, dataManager)
getBzData(client, dataManager)
getRegistryData(client, dataManager)

# 2. Быстрая предзагрузка всех цен AH в оперативную память
print("Загрузка цен AH в оперативную память...", end="", flush=True)
t0 = time.time()
loadedAhCount = 0
for f in dataManager.AH_DIR.glob("*.json"):
    dataManager.itemAhPricesDb[f.stem] = dataManager.loadJson(f)
    loadedAhCount += 1
print(f" Готово ({loadedAhCount} предметов за {time.time() - t0:.2f} сек)")


class ItemProfitStats:
    def __init__(self):
        self.unitCost = 0.0
        self.unitSellPrice = 0.0
        self.targetItemPrice = 0.0
        self.unitProfit = 0.0
        self.roi = 0.0

        self.targetItemVolume = 0.0
        self.dailySales = 0.0
        self.hourlySales = 0.0
        self.targetSellOrders = 0
        self.sellCompScore = 0.0
        self.competitivenessScore = 0.0

        self.bottleneckItem = ""
        self.rawSupplyLimitPerHour = 0.0
        self.hardestBuyItem = ""
        self.buyCompScore = 0.0
        self.rawBuyOrders = 0

        self.effectiveThroughput = 0.0
        self.realProfitPerHour = 0.0
        self.dailyProfitPotential = 0.0
        self.profitPerHours = 0.0
        self.flipScore = 0.0

        self.craftType = "crafting"
        self.durationSec = 0
        self.totalRecipeCost = 0.0
        self.profit = 0.0

        self.totalForgeDurationSec = 0.0
        self.forgeParallelSec = 0.0
        self.forgeBreakdown = {}


PREFIXS = ("INK_SACK-", "LOG-", "LOG_2-1", "RAW_FISH-", "SAND-")
TAX = 0.0125
AH_TAX = 0.02
SAFETY_MARGIN = 1.01
ACTIVE_PLAYER_CRAFT_SPEED = 600.0

FORGE_SLOTS = getattr(config, "forgeSlots", 4)
QUICK_FORGE_PERCENT = getattr(config, "quickForgePercent", 25.0)


def analyzeSingleCraft(
    itemId,
    amount,
    dataManager,
    bzProducts,
    recipesDb,
    printDetails=False,
    forgeSlots=FORGE_SLOTS,
    perkPercent=QUICK_FORGE_PERCENT,
):
    recipe = calculator.get_recipe(itemId, recipesDb)
    if not recipe:
        return None

    totalCost = {}
    craftSteps = {}

    stopList = calculator.findCyclicItems(itemId, recipesDb)
    calculator.calculate_craft(
        itemId, amount, stopList, recipesDb, totalCost, craftSteps
    )

    if not totalCost:
        return None

    stats = ItemProfitStats()
    stats.craftType = recipe.get("type", "crafting")
    stats.durationSec = recipe.get("duration", 0)

    # 1. ПРОДАЖА (ГОТОВЫЙ ТОВАР)
    targetItemInfo = bzProducts.get(itemId)
    if targetItemInfo is not None:
        # Базарный товар
        qs = targetItemInfo.get("quick_status", {})
        targetItemPrice = qs.get("sellPrice", 0)
        stats.targetItemVolume = qs.get("sellVolume", 0)
        weeklySales = max(qs.get("sellMovingWeek", 1), 1)
        stats.hourlySales = weeklySales / 168.0
        stats.dailySales = stats.hourlySales * 24.0
        stats.targetSellOrders = qs.get("sellOrders", 0)
        stats.sellCompScore = stats.targetSellOrders / max(stats.hourlySales, 0.1)
        currentTax = TAX
    else:
        # Аукционный товар (AH)
        ahData = getAhData(itemId, dataManager)
        if not ahData or ahData.get("notFound"):
            return None

        # Для AH берем устойчивую медиану или buy-цену (не берем подозрительно низкий min)
        targetItemPrice = ahData.get("median") or ahData.get("buy") or 0.0

        # Если медиана странная, подстрахуемся
        min_p = ahData.get("min", 0)
        if targetItemPrice <= 0 and min_p > 1000:
            targetItemPrice = min_p

        if targetItemPrice <= 0:
            return None

        stats.dailySales = float(ahData.get("volume", 0) or 0)
        stats.targetItemVolume = stats.dailySales
        stats.hourlySales = max(stats.dailySales / 24.0, 0.01)
        stats.targetSellOrders = 1
        stats.sellCompScore = 1.0
        currentTax = AH_TAX

    stats.unitSellPrice = targetItemPrice
    stats.targetItemPrice = targetItemPrice
    totalProduced = max(craftSteps.get(itemId, amount), 1)

    # 2. ЗАКУПКА СЫРЬЯ
    bottleneckLimit = float("inf")
    bottleneckItem = "N/A"
    worstBuyComp = 0.0
    hardestBuyItem = "N/A"
    worstBuyOrders = 0

    BAZAAR_ORDER_LIMIT = 71680

    for item, reqAmount in totalCost.items():
        key = ":".join(item.split("-", 1)) if item.startswith(PREFIXS) else item
        itemBz = bzProducts.get(key)
        reqPerUnit = reqAmount / totalProduced

        if itemBz is not None:
            sellOrders = itemBz.get("sell_summary", [])
            qs = itemBz.get("quick_status", {})
            bestSellPrice = (
                sellOrders[0].get("pricePerUnit")
                if sellOrders
                else (qs.get("buyPrice") or qs.get("sellPrice") or 0.0)
            )

            if bestSellPrice <= 0:
                bestSellPrice = qs.get("sellPrice", 0.0) or 0.04

            fairPrice = bestSellPrice * 1.01
            cost = reqAmount * fairPrice
            stats.totalRecipeCost += cost

            rawWeeklySupply = max(
                qs.get("sellMovingWeek", 0), qs.get("buyMovingWeek", 0), 1
            )
            rawHourlySupply = rawWeeklySupply / 168.0

            if reqPerUnit > 0:
                maxCraftsFromThisRaw = rawHourlySupply / reqPerUnit
                if maxCraftsFromThisRaw < bottleneckLimit:
                    bottleneckLimit = maxCraftsFromThisRaw
                    bottleneckItem = item

            activeBuyers = qs.get("buyOrders", 0)
            compBuy = activeBuyers / max(rawHourlySupply, 0.1)
            if compBuy > worstBuyComp:
                worstBuyComp = compBuy
                hardestBuyItem = item
                worstBuyOrders = activeBuyers

        elif key in dataManager.notAuctionableIds:
            continue
        else:
            # Ингредиент покупается на AH
            ahInfo = getAhData(key, dataManager)
            ahPrice = (
                ahInfo.get("buy") or ahInfo.get("median") or ahInfo.get("min") or 0.0
            )
            if ahPrice <= 0:
                return None  # Невозможно оценить себестоимость
            cost = reqAmount * ahPrice
            stats.totalRecipeCost += cost

    stats.totalRecipeCost *= SAFETY_MARGIN

    stats.bottleneckItem = bottleneckItem
    stats.rawSupplyLimitPerHour = (
        bottleneckLimit if bottleneckLimit != float("inf") else stats.hourlySales
    )
    stats.hardestBuyItem = hardestBuyItem
    stats.buyCompScore = worstBuyComp
    stats.rawBuyOrders = worstBuyOrders

    # 3. ЭКОНОМИКА 1 ШТУКИ
    stats.unitCost = stats.totalRecipeCost / totalProduced
    netRevenuePerUnit = stats.unitSellPrice * (1.0 - currentTax)
    stats.unitProfit = netRevenuePerUnit - stats.unitCost

    if stats.unitCost > 0:
        stats.roi = (stats.unitProfit / stats.unitCost) * 100.0

    stats.profit = stats.unitProfit * amount

    # 4. РАСЧЕТ ДОХОДНОСТИ
    perkMultiplier = max(1.0 - (perkPercent / 100.0), 0.1)

    if stats.craftType == "forge" and stats.durationSec > 0:
        forgeHoursPerItem = (stats.durationSec * perkMultiplier) / 3600.0
        forgeOutputPerHour = max(forgeSlots, 1) / max(forgeHoursPerItem, 0.001)
        stats.effectiveThroughput = min(
            forgeOutputPerHour, stats.hourlySales, stats.rawSupplyLimitPerHour
        )
    else:
        stats.effectiveThroughput = min(
            ACTIVE_PLAYER_CRAFT_SPEED,
            stats.hourlySales,
            stats.rawSupplyLimitPerHour,
        )

    stats.realProfitPerHour = stats.unitProfit * stats.effectiveThroughput
    stats.profitPerHours = stats.realProfitPerHour
    stats.dailyProfitPotential = stats.unitProfit * min(
        stats.dailySales,
        stats.effectiveThroughput * 24.0 if stats.effectiveThroughput > 0 else 5,
    )

    marketFriction = max(stats.sellCompScore, 0.5) * max(stats.buyCompScore, 0.5)
    stats.flipScore = stats.realProfitPerHour / marketFriction

    return stats


bzProducts = dataManager.itemBzPricesDb.get("products", {})

# ==================== 1. СКАНИРОВАНИЕ АУКЦИОНА (AH CRAFTS) ====================
print("\n" + "#" * 65)
print(" 🏛️ ПОИСК МАРЖИНАЛЬНЫХ КРАФТОВ ДЛЯ АУКЦИОНА (AH FLIPS)")
print("   (Проверено по базе Coflnet: медианная цена + объем продаж)")
print("#" * 65)

whitelistPath = dataManager.BASE_DIR / "ah_craftable_whitelist.json"
ahCraftResults = {}

if whitelistPath.is_file():
    whitelist = dataManager.loadJson(whitelistPath).get("items", [])
    for itemId in whitelist:
        # Проверяем только то, чего нет на Базаре
        if itemId in bzProducts:
            continue

        stats = analyzeSingleCraft(
            itemId,
            1,
            dataManager,
            bzProducts,
            dataManager.itemRecipesDb,
            printDetails=False,
        )

        # Жесткие фильтры качества:
        # 1. Прибыль > 150,000 монет с 1 шт.
        # 2. ROI > 8%
        # 3. Реальный суточный объем продаж > 1.5 шт/день (товар НЕ мертвый)
        if (
            stats
            and stats.unitProfit >= 150_000
            and stats.roi >= 8.0
            and stats.dailySales >= 1.5
        ):
            ahCraftResults[itemId] = stats

# Сортировка 1: По максимальной прибыли с 1 крафта (Крупная рыба)
topProfitAh = sorted(
    ahCraftResults.items(), key=lambda x: x[1].unitProfit, reverse=True
)

# Сортировка 2: По суточному потенциалу заработка (Высокий оборот)
topVelocityAh = sorted(
    ahCraftResults.items(), key=lambda x: x[1].dailyProfitPotential, reverse=True
)

print("\n" + "=" * 65)
print(" 💎 ТОП-10 ПО ЧИСТОЙ ПРИБЫЛИ ЗА 1 КРАФТ (BIG TICKET FLIPS)")
print("=" * 65)

for rank, (item, val) in enumerate(topProfitAh[:10], 1):
    craftTag = f"[{val.craftType.upper()}]"
    print(f"[{rank:>2}] {item:<28} {craftTag:<10}")
    print(
        f"     💰 Чистая прибыль: +{utils.format(val.unitProfit):>7} (ROI: {val.roi:>5.1f}%)"
    )
    print(
        f"     📦 Крафт: {utils.format(val.unitCost):>7}  ➜  Продажа: {utils.format(val.unitSellPrice):>7}"
    )
    print(
        f"     📈 Объем на AH:   ~{val.dailySales:.1f} шт/сутки | Потенциал в день: ~{utils.format(val.dailyProfitPotential)}"
    )
    print("-" * 65)

print("\n" + "=" * 65)
print(" ⚡ ТОП-10 ПО СУТОЧНОМУ ДОХОДУ (HIGH VELOCITY / МАССОВЫЙ КРАФТ)")
print("=" * 65)

for rank, (item, val) in enumerate(topVelocityAh[:10], 1):
    craftTag = f"[{val.craftType.upper()}]"
    print(f"[{rank:>2}] {item:<28} {craftTag:<10}")
    print(f"     🚀 Доход в сутки: ~{utils.format(val.dailyProfitPotential):>7} монет")
    print(
        f"     💰 Прибыль с 1 шт: +{utils.format(val.unitProfit):>7} (ROI: {val.roi:>5.1f}%) | Продаж: {val.dailySales:.1f} шт/день"
    )
    print(
        f"     📦 Крафт: {utils.format(val.unitCost):>7}  ➜  Продажа: {utils.format(val.unitSellPrice):>7}"
    )
    print("-" * 65)
