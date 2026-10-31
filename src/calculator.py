import math

FORBIDDEN_RECIPE_ITEMS = {
    "GOLD_INGOT",
    "IRON_INGOT",
    "DIAMOND",
    "EMERALD",
    "COAL",
    "QUARTZ",
    "NETHER_STALK",
    "PRISMARINE_SHARD",
    "PRISMARINE_CRYSTALS",
}


def get_recipe(itemId, itemsDb):
    if itemId in FORBIDDEN_RECIPE_ITEMS:
        return None

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
        if "ENCHANTED" in itemId or "CONDENSED" in itemId or "Block" in itemId:
            print(f"CRITICAL! RECIPE MISSING FOR {itemId}")
        totalCost[itemId] = totalCost.get(itemId, 0) + amount
        return

    itemsPerCraft = recipe.get("outputCount") or recipe.get("count", 1)
    craftsNeeded = math.ceil(amount / max(itemsPerCraft, 1))

    totalProduced = craftsNeeded * itemsPerCraft
    craftSteps[itemId] = craftSteps.get(itemId, 0) + totalProduced

    # 1. Чтение нормализованных рецептов (RecipeManager: "inputs": { "ID": count })
    if "inputs" in recipe and isinstance(recipe["inputs"], dict):
        for componentId, componentAmount in recipe["inputs"].items():
            totalNeeded = componentAmount * craftsNeeded
            calculate_craft(
                componentId,
                totalNeeded,
                blockedItems,
                itemsDb,
                totalCost,
                craftSteps,
            )

    # 2. Старый формат верстака (A1..C3)
    else:
        keys = ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3"]
        for key, cell in recipe.items():
            if key not in keys:
                continue
            if not isinstance(cell, str) or ":" not in cell:
                continue
            componentId, componentAmountStr = cell.split(":")
            componentAmount = int(componentAmountStr)
            totalNeeded = componentAmount * craftsNeeded
            calculate_craft(
                componentId,
                totalNeeded,
                blockedItems,
                itemsDb,
                totalCost,
                craftSteps,
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

    if "inputs" in recipe and isinstance(recipe["inputs"], dict):
        for componentId in recipe["inputs"].keys():
            findCyclicItems(componentId, itemsDb, currentPath, blockedItems)
    else:
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
