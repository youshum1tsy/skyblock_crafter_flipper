from src import data_manager, calculator

itemsDb = data_manager.loadData()
totalCost = {}
craftSteps = {}

findItem = "SUPER_COMPACTOR_3000"
amount = 1

stopList = calculator.findCyclicItems(findItem, itemsDb)
calculator.calculate_craft(findItem, amount, stopList, itemsDb, totalCost, craftSteps)

for item, count in totalCost.items():
    print(item, count)

for item, count in reversed(list(craftSteps.items())):
    print(f"Craft {item}, amount:{count}")
