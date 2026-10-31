import json
from pathlib import Path
from src import api, data_manager
import config

# Инициализируем данные
dm = data_manager.Data()
dm.loadRecipes()
dm.itemBzPricesDb = dm.loadJson(dm.BZ_FILE_PATH)
dm.itemRegistryDb = dm.loadJson(dm.REGISTRY_FILE_PATH)
dm.filterRegistry()

bzProducts = set(dm.itemBzPricesDb.get("products", {}).keys())
soulboundIds = dm.notAuctionableIds

craftableOutputs = set()
craftableIngredients = set()
noRecipeItems = set()
bazaarItems = set()
soulboundItems = set()

# Проверяем все файлы в папке рецептов
for filePath in dm.RECIPES_DIR.iterdir():
    if not filePath.is_file() or filePath.suffix != ".json":
        continue

    itemId = filePath.stem

    # 1. Если на Базаре
    baseBz = itemId.replace("-", ":")
    if itemId in bzProducts or baseBz in bzProducts:
        bazaarItems.add(itemId)
        continue

    # 2. Если Soulbound
    if itemId in soulboundIds or baseBz in soulboundIds:
        soulboundItems.add(itemId)
        continue

    # Читаем рецепт
    try:
        content = json.loads(filePath.read_text(encoding="utf-8"))
    except Exception:
        continue

    hasRecipe = "recipe" in content or "recipes" in content

    if not hasRecipe:
        noRecipeItems.add(itemId)
    else:
        craftableOutputs.add(itemId)
        # Также собираем все ингредиенты, которые нужны для крафта
        recipesList = dm.itemRecipesDb.get(itemId, [])
        for r in recipesList:
            for ingId in r.get("inputs", {}).keys():
                ingBz = ingId.replace("-", ":")
                if ingBz not in bzProducts and ingId not in soulboundIds:
                    craftableIngredients.add(ingId)
# Суффиксы мобов, боссов и NPC из базы NEU
JUNK_SUFFIXES = (
    "_NPC",
    "_BOSS",
    "_MINIBOSS",
    "_MONSTER",
    "_ANIMAL",
    "_SC",
    "_RIFT_NPC",
)

# Ванильный копеечный мусор (заборы, ступени, двери)
VANILLA_JUNK = (
    "DOOR",
    "FENCE",
    "GATE",
    "STAIRS",
    "CARPET",
    "SLAB",
    "BUTTON",
    "PRESSURE_PLATE",
)


def is_real_ah_item(itemId: str) -> bool:
    # Отсекаем мобов и NPC
    for sfx in JUNK_SUFFIXES:
        if itemId.endswith(sfx) or f"{sfx}_" in itemId:
            return False

    # Отсекаем ванильные стройматериалы
    parts = itemId.split("_")
    for junk in VANILLA_JUNK:
        if junk in parts and "MINERAL" not in itemId:
            return False

    return True


# Фильтруем чистовые крафты и ингредиенты
cleanTargets = {
    item
    for item in craftableOutputs.union(craftableIngredients)
    if is_real_ah_item(item)
}
finalTargetList = sorted(list(cleanTargets))
print("=" * 60)
print("📊 РЕЗУЛЬТАТЫ ПОЛНОГО АУДИТА РЫНКА (8000+ ПРЕДМЕТОВ):")
print("=" * 60)
print(f"1. Базарные предметы (бесплатный API Hypixel):     {len(bazaarItems):>5} шт.")
print(
    f"2. Soulbound / Непередаваемые (нельзя продать):    {len(soulboundItems):>5} шт."
)
print(f"3. Предметы БЕЗ рецепта (чистый лут, дроп, NPC):   {len(noRecipeItems):>5} шт.")
print("-" * 60)
print(
    f"🔥 ЦЕЛЕВЫЕ AH-ПРЕДМЕТЫ ДЛЯ ПРОВЕРКИ COFLNET:        {len(finalTargetList):>5} шт."
)
print(
    f"   (Из них готовых крафтов: {len(craftableOutputs)}, редких деталей: {len(craftableIngredients)})"
)
print("=" * 60)

# Проверка на ошибки: покажем примеры выкинутых "без рецепта"
print(
    "\n👀 Примеры предметов, отсеянных как 'БЕЗ РЕЦЕПТА' (проверь, нет ли тут крафтов):"
)
for ex in list(noRecipeItems)[:15]:
    print(f"  ❌ {ex}")

# Сохраняем расширенный список
whitelistPath = dm.BASE_DIR / "ah_craftable_whitelist.json"
dm.saveJson(
    {"totalCount": len(finalTargetList), "items": finalTargetList},
    whitelistPath,
)
print(
    f"\n✅ Безопасный расширенный список сохранен в: data/ah_craftable_whitelist.json"
)
