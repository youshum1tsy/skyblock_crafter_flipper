from src import data_manager, calculator, api, utils
import config, operator


def getAhData(findItem, dataManager: data_manager.Data):
    ahFilePath = dataManager.AH_DIR / f"{findItem}.json"
    if dataManager.isCacheExpired(ahFilePath):
        dataManager.itemAhPricesDb = api.fetchAhPrices(findItem, config.skyCoflApiToken)
        dataManager.saveJson(dataManager.itemAhPricesDb, ahFilePath)
        print("AH FROM FILE")
    else:
        dataManager.itemAhPricesDb = dataManager.loadJson(ahFilePath)
        print("AH FROM FILE")


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
        self.totalRecipeCost = 0.0
        self.netRevue = 0.0
        self.profit = 0.0
        self.roi = 0.0
        self.targetItemVolume = 0.0
        self.targetItemPrice = 0.0
        self.maxLiqidityHours = 0.0
        self.profitPerHours = 0.0
        self.competitivenessScore = 0.0


def analyzeSingleCraft(itemId, amount, dataManager, bzProducts, recipesDb):

    totalCost = {}
    craftSteps = {}

    stopList = calculator.findCyclicItems(itemId, recipesDb)
    calculator.calculate_craft(
        itemId, amount, stopList, recipesDb, totalCost, craftSteps
    )

    targetItemInfo = bzProducts.get(itemId)
    if not targetItemInfo:
        return None

    qs = targetItemInfo.get("quick_status", {})
    targetItemPrice = qs.get("sellPrice", 0)

    stats = ItemProfitStats()
    stats.targetItemVolume = qs.get("sellVolume", 0)
    stats.targetItemPrice = targetItemPrice

    targetWeeklyVolume = max(qs.get("sellMovingWeek", 1), 1)
    targetHourlySales = max(targetWeeklyVolume / 168, 0.1)
    targetActiveSellers = qs.get("sellOrders", 0)
    stats.competitivenessScore = targetActiveSellers / targetHourlySales

    print(30 * "-")
    print(f"ITEM: {itemId}")
    for item, reqAmount in totalCost.items():
        key = ":".join(item.split("-", 1)) if item.startswith(PREFIXS) else item
        itemBz = bzProducts.get(key)

        if itemBz is not None:
            sellOrders = itemBz.get("sell_summary", [])
            bestSellPrice = (
                sellOrders[0].get("pricePerUnit")
                if sellOrders
                else itemBz.get("quick_status").get("sellPrice")
            )
            weeklyVolume = itemBz.get("quick_status").get("buyMovingWeek", 1)
            if weeklyVolume < 300:
                continue
            hoursNeeded = (reqAmount / max(weeklyVolume, 1)) * 168
            stats.maxLiqidityHours = max(stats.maxLiqidityHours, hoursNeeded)

            fairPrice = bestSellPrice * 1.01
            cost = reqAmount * fairPrice
            stats.totalRecipeCost += cost
            print(
                f"Item: {item} | for 1 (bz): {utils.format(fairPrice)} | buy: {utils.format(reqAmount)} | cost: {utils.format(cost)}"
            )

        elif key in dataManager.notAuctionableIds:
            print(
                f"Item: {item} | Amount: {utils.format(reqAmount)} | Soulbound (cost 0 )"
            )
            continue
        else:
            getAhData(key, dataManager)
            ahPrice = dataManager.itemAhPricesDb.get("median", 0)
            cost = reqAmount * ahPrice
            stats.totalRecipeCost += cost
            print(
                f"Item: {item} | from ah: {utils.format(ahPrice)} | cost: {utils.format(cost)}"
            )

    stats.totalRecipeCost *= SAFETY_MARGIN
    stats.netRevue = targetItemPrice * craftAmount * (1 - TAX)
    stats.profit = stats.netRevue - stats.totalRecipeCost
    stats.profitPerHours = stats.profit / max(stats.maxLiqidityHours, 0.5)
    stats.roi = (
        (stats.profit / stats.totalRecipeCost) * 100 if stats.totalRecipeCost > 0 else 0
    )
    for key, value in craftSteps.items():
        print(f"craft {key}, amount: {value}")
    return stats


PREFIXS = ("INK_SACK-", "LOG-", "LOG_2-1", "RAW_FISH-", "SAND-")

TAX = 0.0125
SAFETY_MARGIN = 1.01
# totalRecipeCost = 0

craftAmount = 1000
bzProducts = dataManager.itemBzPricesDb.get("products")
bzItemsLen = len(bzProducts)
bzItemsCount = 0
bestBzItems = {}
for findItem in bzProducts:
    vol = bzProducts.get(findItem, {}).get("quick_status", {}).get("sellMovingWeek", 0)

    if vol < 500:
        continue

    stats = analyzeSingleCraft(
        findItem, craftAmount, dataManager, bzProducts, dataManager.itemRecipesDb
    )

    if stats and stats.profit > 0 and stats.roi > 3:
        bestBzItems[findItem] = stats
        print(f"Good craft: {findItem} | ROI: {stats.roi:.2f}%")
    else:
        print(f"Bad craft: {findItem} ")


sortBestBzItems = dict(
    sorted(
        bestBzItems.items(),
        key=lambda x: (
            # (x[1].roi / max(x[1].competitivenessScore, 0.1)) * x[1].profitPerHours
            x[1].profitPerHours
        ),
    )
)
for key, value in sortBestBzItems.items():
    print("-" * 30)
    print(f"Item: {key}")
    print(f"Net profit: {utils.format(value.profit)}")
    print(f"Roi: {value.roi:.2f}")
    print(f"Efficiency: {utils.format(value.profitPerHours)} coins/hour")
    print(f"Market volume: {utils.format(value.targetItemVolume)} units listed")
    print(
        f"Competition Score: {value.competitivenessScore * 100} (lower is faster to sell)"
    )
    print(f"Crafting cost: {utils.format(value.totalRecipeCost)} coins")


stats = analyzeSingleCraft(
    "ASPECT_OF_THE_END",
    craftAmount,
    dataManager,
    bzProducts,
    dataManager.itemRecipesDb,
)
utils.printPrettyStats("ASPECT_OF_THE_END", stats)
