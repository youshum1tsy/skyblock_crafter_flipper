import io, zipfile, os, shutil, json, pathlib
from datetime import datetime, timedelta


class Data:
    BASE_DIR = pathlib.Path("data")
    ETAG_PATH = BASE_DIR / "eTag.txt"

    RECIPES_DIR = BASE_DIR / "itemsRecipes"
    RECIPES_TEMP_DIR = BASE_DIR / "itemsRecipes_temp"

    AH_DIR = BASE_DIR / "pricesAh"
    BZ_DIR = BASE_DIR / "pricesBz"
    REGISTRY_DIR = BASE_DIR / "itemsRegistry"

    BZ_FILE_PATH = BZ_DIR / "bz.json"
    REGISTRY_FILE_PATH = REGISTRY_DIR / "registry.json"

    def __init__(self):
        self.itemRecipesDb = {}
        self.itemAhPricesDb = {}
        self.itemBzPricesDb = {}
        self.itemRegistryDb = {}
        self.notAuctionableIds = set()
        self.oldETag = self.readETag()

    def readETag(self) -> str:
        if self.ETAG_PATH.is_file():
            return self.ETAG_PATH.read_text(encoding="utf-8")
        return ""

    def writeETag(self, newETag: str) -> None:
        self.ETAG_PATH.write_text(newETag, encoding="utf-8")

    def unpackRecipes(self, itemsBytes: bytes) -> None:
        itemsBuff = io.BytesIO(itemsBytes)

        if self.RECIPES_TEMP_DIR.is_dir():
            shutil.rmtree(str(self.RECIPES_TEMP_DIR))
        self.RECIPES_TEMP_DIR.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(itemsBuff) as itemsZip:
            allZipPath = itemsZip.namelist()
            for path in allZipPath:
                if "/items/" in path and not (path.endswith("/")):
                    itemsFileName = path.split("/items/")[1]
                    filepath = self.RECIPES_TEMP_DIR / itemsFileName
                    filepath.write_bytes(itemsZip.read(path))

        if self.RECIPES_DIR.is_dir():
            shutil.rmtree(str(self.RECIPES_DIR))
        self.RECIPES_TEMP_DIR.rename(self.RECIPES_DIR)

    def loadRecipes(self) -> None:
        for filePath in self.RECIPES_DIR.iterdir():
            if filePath.is_file():
                data = json.loads(filePath.read_text(encoding="utf-8"))
                itemName = filePath.stem
                if data.get("recipe") is not None:
                    self.itemRecipesDb.update({itemName: data.get("recipe")})
                elif data.get("recipes") is not None:
                    self.itemRecipesDb.update({itemName: data.get("recipes")})

    def isCacheExpired(
        self,
        filePath: pathlib.Path,
        cacheDuration: timedelta | int = timedelta(hours=1),
    ) -> bool:

        if isinstance(cacheDuration, int):
            cacheDuration = timedelta(hours=cacheDuration)

        if not filePath.is_file():
            return True
        mtime = filePath.stat().st_mtime
        fileDate = datetime.fromtimestamp(mtime)
        return datetime.now() - fileDate > cacheDuration

    def saveJson(self, dataDict: dict, filePath: pathlib.Path):
        filePath.parent.mkdir(parents=True, exist_ok=True)
        filePath.write_text(json.dumps(dataDict, indent=2), encoding="utf-8")

    def loadJson(self, filePath: pathlib.Path) -> dict:
        if not filePath.is_file():
            return {}
        return json.loads(filePath.read_text(encoding="utf-8"))

    def filterRegistry(self):
        itemList = self.itemRegistryDb.get("items")
        for item in itemList:
            if (
                (item.get("soulbound") is not None)
                or (item.get("can_auction") == False)
                or (item.get("can_trade") == False)
                or (item.get("category") == "SACK")
                or ("_GENERATOR_" in item.get("id"))
            ):
                self.notAuctionableIds.add(item.get("id"))
