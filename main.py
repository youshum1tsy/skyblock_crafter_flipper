from src import data_manager, calculator, api, utils
import config


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


PREFIXS = (
    "INK_SACK-",
    "LOG-1",
    "LOG_2-1",
)

TAX = 0.0125
SAFETY_MARGIN = 1.01
totalRecipeCost = 0


findItem = "ENCHANTED_GOLD_BLOCK"
craftAmount = 100
totalCost = {}
craftSteps = {}
stopList = calculator.findCyclicItems(findItem, dataManager.itemRecipesDb)
calculator.calculate_craft(
    findItem, craftAmount, stopList, dataManager.itemRecipesDb, totalCost, craftSteps
)
# buyorderMax = 71680

bzProducts = dataManager.itemBzPricesDb.get("products")
targetItemPrice = dataManager.itemAhPricesDb.get("median", 0)
targetItemVolume = dataManager.itemAhPricesDb.get("volume", 0)

if bzProducts.get(findItem) is not None:
    targetItemPrice = bzProducts.get(findItem).get("quick_status").get("sellPrice", 0)
    targetItemVolume = bzProducts.get(findItem).get("quick_status").get("sellVolume", 0)
    print(f"--- BZ ---")
else:
    print(f"--- AH ---")

print(f"--- Analyse craft: {findItem} ---")
print(f"Median: {utils.format(targetItemPrice)} ---")

for item, amount in totalCost.items():
    if item.startswith(PREFIXS):
        item = ":".join(item.split("-", 1))

    itemBz = bzProducts.get(item)

    if itemBz is not None:
        qs = itemBz.get("quick_status")
        buyPrice = qs.get("buyPrice")
        sellPrice = qs.get("sellPrice")

        fairPrice = sellPrice + (0.1 * (buyPrice - sellPrice))
        cost = amount * fairPrice
        totalRecipeCost += cost
        print(
            f"Item: {item} | for 1: {utils.format(fairPrice)} | buy: {utils.format(amount)} | cost: {utils.format(cost)}"
        )
    elif item in dataManager.notAuctionableIds:
        print(f"Item: {item} | Amount: {utils.format(amount)} | Soulbound (cost 0)")
    else:
        getAhData(item, dataManager)
        ahPrice = dataManager.itemAhPricesDb.get("median", 0)
        cost = amount * ahPrice
        totalRecipeCost += cost
        print(
            f"Item: {item} | from ah: {utils.format(ahPrice)} | cost: {utils.format(cost)}"
        )

totalRecipeCost *= SAFETY_MARGIN
netRevue = targetItemPrice * craftAmount * (1 - TAX)
profit = netRevue - totalRecipeCost

roi = (profit / totalRecipeCost) * 100 if totalRecipeCost > 0 else 0

print("-" * 30)
print(f"Cost: {utils.format(totalRecipeCost)}")
print(f"Revenue: {utils.format(netRevue)}")
print(f"Profit: {utils.format(profit)}")
print(f"Volume: {utils.format(targetItemVolume)}")
print(f"ROI: {roi:.2f}%")

if profit > 0 and roi > 3:
    print("good craft")
else:
    print("bad craft")
