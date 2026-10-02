from src import data_manager, calculator, api
import config

dataManager = data_manager.Data()

itemsBytes, newETag = api.fetchItems(dataManager.oldETag)

print("get items Recipes")
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


findItem = "TERMINATOR"
amount = 1
totalCost = {}
craftSteps = {}

print("calc stop list")
stopList = calculator.findCyclicItems(findItem, dataManager.itemRecipesDb)
print("calc craft")
calculator.calculate_craft(
    findItem, amount, stopList, dataManager.itemRecipesDb, totalCost, craftSteps
)


for itemRaw, count in totalCost.items():
    print(itemRaw, count)

for itemRaw, count in reversed(list(craftSteps.items())):
    print(f"Craft {itemRaw}, amount:{count}")


print("get ah")
ahFilePath = dataManager.AH_DIR / f"{findItem}.json"
if dataManager.isCacheExpired(ahFilePath):
    dataManager.itemAhPricesDb = api.fetchAhPrices(findItem, config.skyCoflApiToken)
    dataManager.saveJson(dataManager.itemAhPricesDb, ahFilePath)
    print("AH FROM API")
else:
    dataManager.itemAhPricesDb = dataManager.loadJson(ahFilePath)
    print("AH FROM FILE")
print(dataManager.itemAhPricesDb[0])

client = api.HypixelClient(apiKey=config.hypixelApiToken)
print("get bz")
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
print("get registry")
if dataManager.isCacheExpired(dataManager.REGISTRY_FILE_PATH, cacheDuration=24):
    dataManager.itemRegistryDb = client.getSkyblockItems()
    dataManager.saveJson(dataManager.itemRegistryDb, dataManager.REGISTRY_FILE_PATH)
    dataManager.filterRegistry()
    print("SOULBOUND FROM API")
else:
    dataManager.itemRegistryDb = dataManager.loadJson(dataManager.REGISTRY_FILE_PATH)
    dataManager.filterRegistry()
    print("SOULBOUND FROM FILE")
