from src import data_manager, calculator, api
import config

dataManager = data_manager.Data()

itemsBytes, newETag = api.fetchItems(dataManager.oldETag)

findItem = "SUPER_COMPACTOR_3000"
amount = 1
totalCost = {}
craftSteps = {}

if itemsBytes is not None:
    print("from server")
    dataManager.writeItems(itemsBytes)
    dataManager.writeETag(newETag)
    dataManager.loadDataItems()
elif newETag == dataManager.oldETag and newETag is not None:
    dataManager.loadDataItems()
    print("from data")
else:
    print("error")

stopList = calculator.findCyclicItems(findItem, dataManager.itemsDb)
calculator.calculate_craft(
    findItem, amount, stopList, dataManager.itemsDb, totalCost, craftSteps
)

for item, count in totalCost.items():
    print(item, count)

for item, count in reversed(list(craftSteps.items())):
    print(f"Craft {item}, amount:{count}")

ahFilePath = dataManager.AH_DIR / f"{findItem}.json"
if dataManager.isCacheExpired(ahFilePath):
    dataManager.itemAhPricesDb = api.fetchAhPrices(findItem, config.skyCoflApiToken)
    dataManager.savePrice(dataManager.itemAhPricesDb, dataManager.AH_DIR, ahFilePath)
    print("AH FROM API")
else:
    dataManager.itemAhPricesDb = dataManager.loadPrice(ahFilePath)
    print("AH FROM FILE")
print(dataManager.itemAhPricesDb[0])

client = api.HypixelClient(apiKey=config.hypixelApiToken)

if dataManager.isCacheExpired(dataManager.BZ_FILE_PATH):
    dataManager.itemBzPricesDb = client.getBazaarPrices()
    dataManager.savePrice(
        dataManager.itemBzPricesDb,
        dataManager.BZ_DIR,
        dataManager.BZ_FILE_PATH,
    )
    print("BZ FROM API")
else:
    dataManager.itemBzPricesDb = dataManager.loadPrice(dataManager.BZ_FILE_PATH)
    print("BZ FROM FILE")

soulboundItemsDb = client.getSkyblockItems()
print(soulboundItemsDb)  # id : true, false
