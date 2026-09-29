from src import data_manager, calculator, api
import config

eTagDir = "data/"
eTagFileName = "eTag.txt"
oldETag = data_manager.readETag(eTagDir, eTagFileName)

itemsBytes, newETag = api.fetchItems(oldETag)

itemsDir = "data/items/"
itemsDirTemp = "data/items_temp/"
itemsDb = {}
totalCost = {}
craftSteps = {}
findItem = "SUPER_COMPACTOR_3000"
amount = 1

if itemsBytes is not None:
    print("from server")
    data_manager.writeItems(itemsBytes, itemsDir, itemsDirTemp)
    data_manager.writeETag(newETag, eTagDir, eTagFileName)
    itemsDb = data_manager.loadDataItems(itemsDir)
elif newETag == oldETag and newETag is not None:
    itemsDb = data_manager.loadDataItems(itemsDir)
    print("from data")
else:
    print("error")

stopList = calculator.findCyclicItems(findItem, itemsDb)
calculator.calculate_craft(findItem, amount, stopList, itemsDb, totalCost, craftSteps)

for item, count in totalCost.items():
    print(item, count)

for item, count in reversed(list(craftSteps.items())):
    print(f"Craft {item}, amount:{count}")


itemAhPricesDir = "data/pricesAh/"
itemAhPricesExt = ".json"
itemAhPricesPath = itemAhPricesDir + findItem + itemAhPricesExt
itemAhPricesDb = {}
if data_manager.isCacheExpired(itemAhPricesPath):
    itemAhPricesDb = api.fetchAhPrices(findItem, config.skyCoflApiToken)
    data_manager.savePrice(itemAhPricesDb, itemAhPricesDir, itemAhPricesPath)
    print("AH FROM API")
else:
    itemAhPricesDb = data_manager.loadPrice(itemAhPricesPath)
    print("AH FROM FILE")
print(itemAhPricesDb[0])
data_manager.savePrice(itemAhPricesDb, itemAhPricesDir, itemAhPricesPath)

itemBzPricesDir = "data/pricesBz/"
itemBzPricesExt = ".json"
itemBzPricesPath = f"{itemBzPricesDir}bz{itemBzPricesExt}"
itemBzPricesDb = {}
if data_manager.isCacheExpired(itemBzPricesPath):
    itemBzPricesDb = api.fetchBzPrices(config.hypixelApiToken)
    data_manager.savePrice(itemBzPricesDb, itemBzPricesDir, itemBzPricesPath)
    print("BZ FROM API")
else:
    itemBzPricesDb = data_manager.loadPrice(itemBzPricesPath)
    print("BZ FROM FILE")
print(itemBzPricesDb.get("success"))
