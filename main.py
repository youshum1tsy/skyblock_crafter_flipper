import math
from src import data_manager, calculator, api, utils
import config


def getAhData(findItem: str, dataManager: data_manager.Data) -> dict:
    """Кэширует цены с аукциона (Coflnet API) поштучно в память и файл."""
    if findItem in dataManager.itemAhPricesDb:
        return dataManager.itemAhPricesDb[findItem]

    ahFilePath = dataManager.AH_DIR / f"{findItem}.json"
    if dataManager.isCacheExpired(ahFilePath):
        priceData = api.fetchAhPrices(findItem, config.skyCoflApiToken)
        if priceData:
            dataManager.saveJson(priceData, ahFilePath)
            print(f"AH FROM API: {findItem}")
    else:
        priceData = dataManager.loadJson(ahFilePath)
        print(f"AH FROM FILE: {findItem}")

    dataManager.itemAhPricesDb[findItem] = priceData or {}
    return dataManager.itemAhPricesDb[findItem]


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


client = api.HypixelClient(apiKey=config.hypixelApiToken)
dataManager = data_manager.Data()
itemsBytes, newETag = api.fetchItems(dataManager.oldETag)

getRecipeData(itemsBytes, newETag, dataManager)
getBzData(client, dataManager)
getRegistryData(client, dataManager)


class ItemProfitStats:
    def __init__(self):
        # 1. Экономика 1 штуки
        self.unitCost = 0.0
        self.unitSellPrice = 0.0
        self.targetItemPrice = 0.0  # Для utils.py
        self.unitProfit = 0.0
        self.roi = 0.0

        # 2. ПРОДАЖА ГОТОВОГО ТОВАРА (SELL PHASE)
        self.targetItemVolume = 0.0
        self.hourlySales = 0.0  # Спрос на готовый товар (шт/час)
        self.targetSellOrders = 0  # Сколько лотов выставлено на продажу
        self.sellCompScore = 0.0  # Конкуренция на ПРОДАЖУ готового товара
        self.competitivenessScore = 0.0  # Для совместимости

        # 3. ЗАКУПКА СЫРЬЯ (BUY PHASE)
        self.bottleneckItem = ""  # Самый дефицитный ингредиент (по объему)
        self.rawSupplyLimitPerHour = 0.0  # Макс. крафтов в час по притоку сырья
        self.hardestBuyItem = ""  # Самый конкурентный ингредиент (где война ордеров)
        self.buyCompScore = 0.0  # Конкуренция на ЗАКУПКУ сырья
        self.rawBuyOrders = 0  # Активных бай-ордеров на проблемном сырье

        # 4. РЕЗУЛЬТАТЫ И СКОРИНГ
        self.effectiveThroughput = 0.0  # Реальный объем в час (с учетом всех лимитов)
        self.realProfitPerHour = 0.0  # Честный доход в час
        self.profitPerHours = 0.0  # Для utils.py
        self.flipScore = 0.0  # Двусторонний индекс привлекательности

        # Тип крафта и время кузницы
        self.craftType = "crafting"
        self.durationSec = 0
        self.totalRecipeCost = 0.0
        self.profit = 0.0

        self.totalForgeDurationSec = (
            0.0  # Суммарное время кузницы (в 1 слот без перков)
        )
        self.forgeParallelSec = 0.0  # Время с учетом слотов и перка
        self.forgeBreakdown = {}  # Разбивка по деталям


PREFIXS = ("INK_SACK-", "LOG-", "LOG_2-1", "RAW_FISH-", "SAND-")
TAX = 0.0125
AH_TAX = 0.02
SAFETY_MARGIN = 1.01

ACTIVE_PLAYER_CRAFT_SPEED = 600.0  # Лимит скорости рук: ~10 крафтов в минуту

# ==================== НАСТРОЙКИ КУЗНИЦЫ (FORGE CONFIG) ====================
FORGE_SLOTS = getattr(config, "forgeSlots", 4)  # Твоё количество слотов (от 1 до 5)
QUICK_FORGE_PERCENT = getattr(
    config, "quickForgePercent", 25.0
)  # Перк ускорения HotM в % (например, 20 или 30)


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

    # ==================== 1. ЭТАП ПРОДАЖИ (ГОТОВЫЙ ТОВАР) ====================
    targetItemInfo = bzProducts.get(itemId)
    if targetItemInfo is not None:
        qs = targetItemInfo.get("quick_status", {})
        targetItemPrice = qs.get("sellPrice", 0)
        stats.targetItemVolume = qs.get("sellVolume", 0)

        # Спрос на готовый товар
        weeklySales = max(qs.get("sellMovingWeek", 1), 1)
        stats.hourlySales = weeklySales / 168.0

        # Конкуренция на ПРОДАЖУ готового товара
        stats.targetSellOrders = qs.get("sellOrders", 0)
        stats.sellCompScore = stats.targetSellOrders / max(stats.hourlySales, 0.1)
        stats.competitivenessScore = stats.sellCompScore
        currentTax = TAX
    else:
        # Аукционный товар
        ahData = getAhData(itemId, dataManager)
        min_p = ahData.get("min", 0)
        targetItemPrice = (
            ahData.get("buy") or ahData.get("median") or (min_p if min_p > 1000 else 0)
        )
        if targetItemPrice <= 0:
            return None
        stats.targetItemVolume = ahData.get("volume", 0)
        stats.hourlySales = max(stats.targetItemVolume / 24.0, 0.1)
        stats.targetSellOrders = 1
        stats.sellCompScore = 1.0
        stats.competitivenessScore = 1.0
        currentTax = AH_TAX

    stats.unitSellPrice = targetItemPrice
    stats.targetItemPrice = targetItemPrice
    totalProduced = max(craftSteps.get(itemId, amount), 1)

    if printDetails:
        print("\n" + "=" * 60)
        print(
            f"ЦЕЛЕВОЙ ПРЕДМЕТ: {itemId} (Количество: {amount} шт.) [{stats.craftType.upper()}]"
        )
        print(f"Рыночная цена продажи (1 шт): {utils.format(targetItemPrice)} монет")
        print("-" * 60)
        print("🛒 СПИСОК ЗАКУПКИ СЫРЬЯ (С БАЗАРА / AH):")

    # ==================== 2. ЭТАП ЗАКУПКИ (СЫРЬЕ И ИНГРЕДИЕНТЫ) ====================
    bottleneckLimit = float("inf")
    bottleneckItem = "N/A"
    worstBuyComp = 0.0
    hardestBuyItem = "N/A"
    worstBuyOrders = 0

    BAZAAR_ORDER_LIMIT = 71680  # Максимальная вместимость одного Buy Order на Базаре

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

            # Поставки сырья (учитываем максимальный реальный приток)
            rawWeeklySupply = max(
                qs.get("sellMovingWeek", 0), qs.get("buyMovingWeek", 0), 1
            )
            rawHourlySupply = rawWeeklySupply / 168.0

            # 2.1 Проверка дефицита объема
            if reqPerUnit > 0:
                maxCraftsFromThisRaw = rawHourlySupply / reqPerUnit
                if maxCraftsFromThisRaw < bottleneckLimit:
                    bottleneckLimit = maxCraftsFromThisRaw
                    bottleneckItem = item

            # 2.2 Проверка войны за закупку сырья (Buy Comp Score)
            activeBuyers = qs.get("buyOrders", 0)
            compBuy = activeBuyers / max(rawHourlySupply, 0.1)

            if compBuy > worstBuyComp:
                worstBuyComp = compBuy
                hardestBuyItem = item
                worstBuyOrders = activeBuyers

            # Расчёт количества Buy Order'ов (макс 71680)
            exactAmount = int(round(reqAmount))
            if exactAmount > BAZAAR_ORDER_LIMIT:
                fullOrders = exactAmount // BAZAAR_ORDER_LIMIT
                rem = exactAmount % BAZAAR_ORDER_LIMIT
                if rem > 0:
                    ordersText = f"{fullOrders + 1} орд. ({fullOrders}x {BAZAAR_ORDER_LIMIT} + {rem})"
                else:
                    ordersText = f"{fullOrders} орд. по {BAZAAR_ORDER_LIMIT}"
            else:
                ordersText = f"{exactAmount}"

            if printDetails:
                print(
                    f"  • {item:<22} | Цена: {utils.format(fairPrice):>7} | Всего: {utils.format(reqAmount):>7} | Ордера: {ordersText:<32} | Сумма: {utils.format(cost):>9}"
                )

        elif key in dataManager.notAuctionableIds:
            if printDetails:
                print(f"  • {item:<22} | Soulbound (Бесплатно / Личный предмет)")
            continue
        else:
            ahInfo = getAhData(key, dataManager)
            min_p = ahInfo.get("min", 0)
            ahPrice = (
                ahInfo.get("buy")
                or ahInfo.get("median")
                or (min_p if min_p > 1000 else 0)
            )
            cost = reqAmount * ahPrice
            stats.totalRecipeCost += cost
            if printDetails:
                exactAhAmount = int(round(reqAmount))
                print(
                    f"  • {item:<22} | С АУКЦИОНА: {utils.format(ahPrice):>7} | Купить: {exactAhAmount:>5} шт | {'(Купить на AH)':<32} | Сумма: {utils.format(cost):>9}"
                )

    stats.totalRecipeCost *= SAFETY_MARGIN

    # Сохраняем раздельные метрики закупки сырья
    stats.bottleneckItem = bottleneckItem
    stats.rawSupplyLimitPerHour = (
        bottleneckLimit if bottleneckLimit != float("inf") else stats.hourlySales
    )
    stats.hardestBuyItem = hardestBuyItem
    stats.buyCompScore = worstBuyComp
    stats.rawBuyOrders = worstBuyOrders

    # ==================== 3. ЭКОНОМИКА 1 ШТУКИ ====================
    stats.unitCost = stats.totalRecipeCost / totalProduced
    netRevenuePerUnit = stats.unitSellPrice * (1.0 - currentTax)
    stats.unitProfit = netRevenuePerUnit - stats.unitCost

    if stats.unitCost > 0:
        stats.roi = (stats.unitProfit / stats.unitCost) * 100.0

    stats.profit = stats.unitProfit * amount

    # ==================== 4. РАСЧЕТ РЕАЛЬНОГО ДОХОДА И ДВУСТОРОННИЙ FLIP SCORE ====================
    perkMultiplier = max(1.0 - (perkPercent / 100.0), 0.1)

    if stats.craftType == "forge" and stats.durationSec > 0:
        # Учитываем время с перком и количество слотов
        forgeHoursPerItem = (stats.durationSec * perkMultiplier) / 3600.0
        forgeOutputPerHour = max(forgeSlots, 1) / max(forgeHoursPerItem, 0.001)
        stats.effectiveThroughput = min(
            forgeOutputPerHour, stats.hourlySales, stats.rawSupplyLimitPerHour
        )
    else:
        # Верстак: руки (600), спрос готового И приток сырья
        stats.effectiveThroughput = min(
            ACTIVE_PLAYER_CRAFT_SPEED,
            stats.hourlySales,
            stats.rawSupplyLimitPerHour,
        )

    stats.realProfitPerHour = stats.unitProfit * stats.effectiveThroughput
    stats.profitPerHours = stats.realProfitPerHour

    # ДВУСТОРОННИЙ FLIP SCORE: штрафует товар за войну на ПРОДАЖЕ или ЗАКУПКЕ
    marketFriction = max(stats.sellCompScore, 0.5) * max(stats.buyCompScore, 0.5)
    stats.flipScore = stats.realProfitPerHour / marketFriction

    if printDetails:
        print("-" * 60)
        print("🔨 ПОШАГОВЫЙ ПЛАН КРАФТА (ОТ СЫРЬЯ К ФИНАЛУ):")
        sortedSteps = sorted(craftSteps.items(), key=lambda x: x[1], reverse=True)
        for stepKey, stepVal in sortedSteps:
            print(f"  ➜ Скрафтить: {stepKey:<25} x{stepVal}")

    # ==================== 5. ПОДСЧЕТ ВРЕМЕНИ В КУЗНИЦЕ (С УЧЕТОМ СЛОТОВ И ПЕРКА) ====================
    totalForgeDurationSec = 0.0
    forgeBreakdown = {}

    for stepItem, stepAmount in craftSteps.items():
        stepRecipe = calculator.get_recipe(stepItem, recipesDb)
        if stepRecipe and stepRecipe.get("type") == "forge":
            dur = stepRecipe.get("duration", 0)
            outCount = stepRecipe.get("outputCount") or stepRecipe.get("count", 1)
            craftsCount = math.ceil(stepAmount / max(outCount, 1))
            itemTotalSec = craftsCount * dur

            if itemTotalSec > 0:
                totalForgeDurationSec += itemTotalSec
                forgeBreakdown[stepItem] = {
                    "amount": stepAmount,
                    "unitDuration": dur,
                    "totalSec": itemTotalSec,
                }

    totalWithPerkSec = totalForgeDurationSec * perkMultiplier
    parallelSec = totalWithPerkSec / max(forgeSlots, 1)

    stats.totalForgeDurationSec = totalForgeDurationSec
    stats.forgeParallelSec = parallelSec
    stats.forgeBreakdown = forgeBreakdown

    # Если включен подробный вывод — печатаем красивую статистику времени
    if printDetails and totalForgeDurationSec > 0:
        baseParallel = totalForgeDurationSec / max(forgeSlots, 1)

        print("-" * 60)
        print("⏱ ВРЕМЯ В КУЗНИЦЕ (FORGE TIME):")
        print(
            f"  • Настройки: {forgeSlots} слотов | Перк Quick Forge: -{perkPercent:.0f}%"
        )
        print(
            f"  • Базовое время (в 1 слот без перка):   {utils.format_time(totalForgeDurationSec)} ({totalForgeDurationSec / 3600:.1f} ч)"
        )
        print(
            f"  • В {forgeSlots} слотов (без перка):          ~{utils.format_time(baseParallel)} ({baseParallel / 3600:.1f} ч)"
        )
        print(
            f"  • РЕАЛЬНОЕ ВРЕМЯ ({forgeSlots} слотов + -{perkPercent:.0f}%):  🔥 ~{utils.format_time(parallelSec)} ({parallelSec / 3600:.1f} ч)"
        )
        print(f"\n  📋 Подетальная разбивка (с учетом перка -{perkPercent:.0f}%):")

        # Сортируем: сначала самые долгие детали
        sortedForge = sorted(
            forgeBreakdown.items(), key=lambda x: x[1]["totalSec"], reverse=True
        )
        for fItem, fData in sortedForge:
            unitWithPerk = fData["unitDuration"] * perkMultiplier
            totalWithPerk = fData["totalSec"] * perkMultiplier
            unitT = utils.format_time(unitWithPerk)
            totalT = utils.format_time(totalWithPerk)
            print(
                f"    ➜ {fItem:<24} x{fData['amount']:<4} | Всего: {totalT:>8} (по {unitT} на 1 шт)"
            )

    return stats


# ==================== СКАНИРОВАНИЕ БАЗАРА ====================
print("\n" + "=" * 20 + " СКАНИРОВАНИЕ БАЗАРА " + "=" * 20)
bzProducts = dataManager.itemBzPricesDb.get("products", {})

activeCraftingItems = {}
passiveForgeItems = {}

for findItem in bzProducts:
    vol = bzProducts.get(findItem, {}).get("quick_status", {}).get("sellMovingWeek", 0)
    if vol < 500:
        continue

    stats = analyzeSingleCraft(
        findItem,
        1,
        dataManager,
        bzProducts,
        dataManager.itemRecipesDb,
        printDetails=False,
    )

    if stats and stats.unitProfit > 0 and stats.roi > 3:
        if stats.craftType == "forge" and stats.durationSec > 0:
            passiveForgeItems[findItem] = stats
        else:
            activeCraftingItems[findItem] = stats
        print(
            f"✓ [{stats.craftType[:4].upper()}] {findItem:<26} | Профит: {utils.format(stats.unitProfit):>7} | ROI: {stats.roi:>6.1f}% | Скор: {utils.format(stats.flipScore)}"
        )


# Сортировка по двустороннему Flip Score
sortActive = dict(
    sorted(activeCraftingItems.items(), key=lambda x: x[1].flipScore, reverse=True)
)
sortForge = dict(
    sorted(passiveForgeItems.items(), key=lambda x: x[1].flipScore, reverse=True)
)


# ==================== ТАБЛИЦА 1: РУЧНОЙ АКТИВНЫЙ ФЛИП (ВЕРСТАК) ====================
print("\n" + "#" * 60)
print(" 🔥 ТОП-10 ДЛЯ АКТИВНОГО РУЧНОГО ФЛИПА (ВЕРСТАК)")
print("   (Учитывает спрос, дефицит сырья И конкуренцию с обеих сторон)")
print("#" * 60)

for rank, (key, value) in enumerate(list(sortActive.items())[:10], 1):
    sellComp = value.sellCompScore
    buyComp = value.buyCompScore
    rawLimit = value.rawSupplyLimitPerHour

    if rawLimit < 50:
        badge = f"⚠️ ДЕФИЦИТ СЫРЬЯ ({value.bottleneckItem})"
    elif buyComp > 2.0:
        badge = f"⚔️ ВОЙНА НА ЗАКУПКЕ СЫРЬЯ ({value.hardestBuyItem})"
    elif sellComp > 2.0:
        badge = "🔴 АНДЕРКАТ НА ПРОДАЖЕ"
    elif sellComp <= 0.8 and buyComp <= 0.8:
        badge = "⚡ ИДЕАЛЬНЫЙ ОБОРОТ (Скупки и продажи свободны)"
    else:
        badge = "🟢 СТАБИЛЬНЫЙ ФЛИП"

    print("-" * 55)
    print(f"[{rank:>2}] {key:<30} {badge}")
    print("-" * 55)
    print(
        f"  💰 Чистая прибыль (1 шт):   +{utils.format(value.unitProfit)} монет (ROI: {value.roi:.1f}%)"
    )
    print(
        f"  📦 Себестоимость крафта:    {utils.format(value.unitCost)}  ➜  Продажа: {utils.format(value.unitSellPrice)}"
    )

    # 1. Блок продажи готового товара
    sellStatus = (
        "Очереди нет (Мгновенно)"
        if sellComp < 0.5
        else "Умеренно"
        if sellComp < 2.0
        else "Очередь продавцов"
    )
    print(
        f"  📤 ПРОДАЖА ГОТОВОГО ТОВАРА: Спрос: {utils.format(value.hourlySales)} шт/час | Sell Comp: {sellComp:.2f} ({sellStatus})"
    )

    # 2. Блок закупки сырья
    buyStatus = (
        "Сырьё отдают сразу"
        if buyComp < 0.5
        else "Умеренно"
        if buyComp < 2.0
        else "Война бай-ордеров"
    )
    print(
        f"  📥 ЗАКУПКА СЫРЬЯ:           Лимит: {utils.format(rawLimit)} шт/час | Buy Comp: {buyComp:.2f} ({buyStatus})"
    )
    if buyComp > 1.0:
        print(
            f"     └─ Самый конкурентный ингредиент: {value.hardestBuyItem} ({value.rawBuyOrders} активных бай-ордеров)"
        )

    print(
        f"  🚀 РЕАЛЬНЫЙ ДОХОД В ЧАС:    ~{utils.format(value.realProfitPerHour)} монет/час (руками)"
    )


# ==================== ТАБЛИЦА 2: ПАССИВНЫЙ ЗАРАБОТОК (КУЗНИЦА) ====================
print("\n" + "#" * 60)
print(f" ⚙️ ТОП-10 ДЛЯ КУЗНИЦЫ (FORGE / {FORGE_SLOTS} СЛОТОВ ПАССИВНО)")
print("#" * 60)

for rank, (key, value) in enumerate(list(sortForge.items())[:10], 1):
    durHours = value.durationSec / 3600.0
    print("-" * 55)
    print(f"[{rank:>2}] {key:<30} ⏱ Время плавки 1 шт: {durHours:.1f}ч")
    print("-" * 55)
    print(
        f"  💰 Чистая прибыль (1 шт):   +{utils.format(value.unitProfit)} монет (ROI: {value.roi:.1f}%)"
    )
    print(
        f"  📦 Себестоимость крафта:    {utils.format(value.unitCost)}  ➜  Продажа: {utils.format(value.unitSellPrice)}"
    )
    print(
        f"  📤 Продажа (Sell Comp):     {value.sellCompScore:.2f} | 📥 Закупка сырья (Buy Comp): {value.buyCompScore:.2f}"
    )
    print(
        f"  💤 ПАССИВНЫЙ ДОХОД В ЧАС:   ~{utils.format(value.realProfitPerHour)} монет/час (со всех {FORGE_SLOTS} слотов)"
    )


# ==================== ТОЧЕЧНЫЕ ПРОВЕРКИ ====================


print("\n" + "=" * 20 + " ТОЧЕЧНАЯ ПРОВЕРКА: DRILL X355 " + "=" * 20)
stats_drill = analyzeSingleCraft(
    "TITANIUM_DRILL_1",
    1,
    dataManager,
    bzProducts,
    dataManager.itemRecipesDb,
    printDetails=True,
)
utils.printPrettyStats("TITANIUM_DRILL_1", stats_drill)

print("\n" + "=" * 20 + " ТОЧЕЧНАЯ ПРОВЕРКА: REFIND MITHRIL " + "=" * 20)
stats_drill = analyzeSingleCraft(
    "REFIND_MITHRIL",
    8,
    dataManager,
    bzProducts,
    dataManager.itemRecipesDb,
    printDetails=True,
)
utils.printPrettyStats("REFIND_MITHRIL", stats_drill)

print("\n" + "=" * 20 + " ТОЧЕЧНАЯ ПРОВЕРКА: REFIND TITANIUM " + "=" * 20)
stats_drill = analyzeSingleCraft(
    "REFIND_TITANIUM",
    8,
    dataManager,
    bzProducts,
    dataManager.itemRecipesDb,
    printDetails=True,
)
utils.printPrettyStats("REFIND_TITANIUM", stats_drill)

print("\n" + "=" * 20 + " ТОЧЕЧНАЯ ПРОВЕРКА: GOLDEN PLATE " + "=" * 20)
stats_bale = analyzeSingleCraft(
    "GOLDEN_PLATE",
    6,
    dataManager,
    bzProducts,
    dataManager.itemRecipesDb,
    printDetails=True,
)
utils.printPrettyStats("GOLDEN_PLATE", stats_bale)
