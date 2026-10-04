from src import data_manager, calculator, api
import config

dataManager = data_manager.Data()

itemsBytes, newETag = api.fetchItems(dataManager.oldETag)


def getAhData(findItem):
    ahFilePath = dataManager.AH_DIR / f"{findItem}.json"
    if dataManager.isCacheExpired(ahFilePath):
        dataManager.itemAhPricesDb = api.fetchAhPrices(findItem, config.skyCoflApiToken)
        dataManager.saveJson(dataManager.itemAhPricesDb, ahFilePath)
        print("AH FROM FILE")
    else:
        dataManager.itemAhPricesDb = dataManager.loadJson(ahFilePath)
        print("AH FROM FILE")


def getBzData():
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


def getRegistryData():
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


if itemsBytes is None and dataManager.RECIPES_DIR.is_dir():
    dataManager.loadRecipes()
    print("from data")
else:
    if itemsBytes is None:
        itemsBytes, newETag = api.fetchItems(eTag="")
    print("from server")
    dataManager.unpackRecipes(itemsBytes)
    dataManager.writeETag(newETag)
    dataManager.loadRecipes()


findItem = "ENCHANTED_GOLD_BLOCK"
craftAmount = 5
totalCost = {}
craftSteps = {}

stopList = calculator.findCyclicItems(findItem, dataManager.itemRecipesDb)
calculator.calculate_craft(
    findItem, craftAmount, stopList, dataManager.itemRecipesDb, totalCost, craftSteps
)

getAhData(findItem)
client = api.HypixelClient(apiKey=config.hypixelApiToken)
getBzData()
getRegistryData()

PREFIXS = (
    "INK_SACK-",
    "LOG-1",
    "LOG_2-1",
)

TAX = 0.0125
SAFETY_MARGIN = 1.01
totalRecipeCost = 0


bzProducts = dataManager.itemBzPricesDb.get("products")
targetItemPrice = dataManager.itemAhPricesDb.get("median", 0)
targetItemVolume = dataManager.itemAhPricesDb.get("volume", 0)

if bzProducts.get(findItem) is not None:
    targetItemPrice = bzProducts.get("quick_status").get("sellPrice", 0)
    targetItemVolume = bzProducts.get("quick_status").get("sellVolume", 0)
    print(f"--- BZ ---")
else:
    print(f"--- AH ---")

print(f"--- Analyse craft: {findItem} ---")
print(f"Median: {targetItemPrice:,.0f} ---")

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
        print(f"Item: {item} | for 1 {fairPrice:.2f} | cost: {cost}")
    elif item in dataManager.notAuctionableIds:
        print(f"Item: {item} | Amount: {amount} | Soulbound (cost 0)")
    else:
        getAhData(item)
        ahPrice = dataManager.itemAhPricesDb.get("median", 0)
        cost = amount * ahPrice
        totalRecipeCost += cost
        print(f"Item: {item} {ahPrice} from ah | cost: {cost:.0f}")

totalRecipeCost *= SAFETY_MARGIN
netRevue = targetItemPrice * craftAmount * (1 - TAX)
profit = netRevue - totalRecipeCost

roi = (profit / totalRecipeCost) * 100 if totalRecipeCost > 0 else 0

print("-" * 30)
print(f"Cost: {totalRecipeCost:.0f}")
print(f"Revenue: {netRevue:.0f}")
print(f"Profit: {profit:0f}")
print(f"Volume: {targetItemVolume}")
print(f"ROI: {roi:.2f}%")

if profit > 0 and roi > 3:
    print("good craft")
else:
    print("bad craft")
