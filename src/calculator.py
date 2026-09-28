import math


def get_recipe(itemId, itemsDb):
    rawRecipe = itemsDb.get(itemId)

    if isinstance(rawRecipe, list):
        if len(rawRecipe) > 0:
            return rawRecipe[0]
        else:
            return None
    return rawRecipe


def calculate_craft(itemId, amount, blockedItems, itemsDb, totalCost, craftSteps):

    if itemId in blockedItems:
        totalCost[itemId] = totalCost.get(itemId, 0) + amount
        return

    recipe = get_recipe(itemId, itemsDb)

    if recipe is None:
        totalCost[itemId] = totalCost.get(itemId, 0) + amount
        return

    itemsPerCraft = recipe.get("count", 1)
    craftsNeeded = math.ceil(amount / itemsPerCraft)

    totalProduced = craftsNeeded * itemsPerCraft
    craftSteps[itemId] = craftSteps.get(itemId, 0) + totalProduced

    for cell in recipe.values():
        if not isinstance(cell, str) or ":" not in cell:
            continue
        componentId, componentAmountStr = cell.split(":")
        componentAmount = int(componentAmountStr)
        totalNeeded = componentAmount * craftsNeeded
        calculate_craft(
            componentId, totalNeeded, blockedItems, itemsDb, totalCost, craftSteps
        )


def findCyclicItems(itemId, itemsDb, currentPath=None, blockedItems=None):
    if currentPath is None:
        currentPath = []
    if blockedItems is None:
        blockedItems = set()

    if itemId in currentPath:
        blockedItems.add(itemId)
        return blockedItems

    recipe = get_recipe(itemId, itemsDb)
    if recipe is None:
        return blockedItems

    currentPath.append(itemId)

    for cell in recipe.values():
        if not isinstance(cell, str) or ":" not in cell:
            continue
        componentId, _ = cell.split(":")

        findCyclicItems(
            componentId,
            itemsDb,
            currentPath,
            blockedItems,
        )

    currentPath.pop()

    return blockedItems
