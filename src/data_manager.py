import io, zipfile, os, shutil, json, pathlib
from datetime import datetime, timedelta


class Data:
    BASE_DIR = pathlib.Path("data")
    ETAG_PATH = BASE_DIR / "eTag.txt"
    ITEMS_DIR = BASE_DIR / "items"
    ITEMS_TEMP_DIR = BASE_DIR / "items_temp"

    AH_DIR = BASE_DIR / "pricesAh"
    BZ_DIR = BASE_DIR / "pricesBz"

    BZ_FILE_PATH = BZ_DIR / "bz.json"

    def __init__(self):
        self.itemsDb = {}
        self.itemAhPricesDb = {}
        self.itemBzPricesDb = {}
        self.oldETag = self.readETag()

    def readETag(self) -> str:
        if self.ETAG_PATH.is_file():
            return self.ETAG_PATH.read_text(encoding="utf-8")
        return ""

    def writeETag(self, newETag: str) -> None:
        self.ETAG_PATH.write_text(newETag, encoding="utf-8")

    def writeItems(self, itemsBytes: bytes) -> None:
        itemsBuff = io.BytesIO(itemsBytes)

        if self.ITEMS_TEMP_DIR.is_dir():
            shutil.rmtree(str(self.ITEMS_TEMP_DIR))
        self.ITEMS_TEMP_DIR.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(itemsBuff) as itemsZip:
            allZipPath = itemsZip.namelist()
            for path in allZipPath:
                if "/items/" in path and not (path.endswith("/")):
                    itemsFileName = path.split("/items/")[1]
                    filepath = self.ITEMS_TEMP_DIR / itemsFileName
                    with open(filepath, "wb") as file:
                        file.write(itemsZip.read(path))

        if self.ITEMS_DIR.is_dir():
            shutil.rmtree(str(self.ITEMS_DIR))
        os.rename(str(self.ITEMS_TEMP_DIR), str(self.ITEMS_DIR))

    def loadDataItems(self) -> None:
        for filePath in self.ITEMS_DIR.iterdir():
            if filePath.is_file():
                with open(file=(str(filePath)), mode="r", encoding="utf-8") as f:
                    data = json.load(f)
                itemName = filePath.stem
                if data.get("recipe") != None:
                    self.itemsDb.update({itemName: data.get("recipe")})
                elif data.get("recipes") != None:
                    self.itemsDb.update({itemName: data.get("recipes")})

    def isCacheExpired(
        self,
        itemPricesPath: pathlib.Path,
        cacheDuration: timedelta = timedelta(hours=1),
    ) -> bool:
        if not itemPricesPath.is_file():
            return True
        mtime = os.path.getmtime(itemPricesPath)
        fileDate = datetime.fromtimestamp(mtime)
        return datetime.now() - fileDate > cacheDuration

    def savePrice(
        self, itemPrices: dict, itemPricesDir: pathlib.Path, itemPricePath: pathlib.Path
    ):
        itemPricesDir.mkdir(parents=True, exist_ok=True)

        with open(str(itemPricePath), mode="w", encoding="utf-8") as file:
            json.dump(itemPrices, file, indent=2)

    def loadPrice(self, itemPricePath: pathlib.Path) -> dict:
        prices = {}
        with open(str(itemPricePath), mode="r", encoding="utf-8") as f:
            prices = json.load(f)
        return prices
