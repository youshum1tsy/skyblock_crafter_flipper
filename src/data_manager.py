import io, zipfile, os, shutil, json
from datetime import datetime, timedelta


def readETag(eTagDir: str, eTagFileName: str) -> str:
    eTag = ""
    if os.path.isfile(eTagDir + eTagFileName):
        with open(file=(eTagDir + eTagFileName), mode="r", encoding="utf-8") as file:
            eTag = file.read()
        return eTag
    return eTag


def writeETag(newETag: str, eTagDir: str, eTagFileName: str):
    with open(file=(eTagDir + eTagFileName), mode="w", encoding="utf-8") as file:
        file.write(newETag)


def writeItems(itemsBytes: bytes, itemsDir: str, itemsDirTemp: str):
    itemsBuff = io.BytesIO(itemsBytes)
    if not (os.path.isdir("data")):
        os.mkdir("data")

    if not (os.path.isdir(itemsDirTemp)):
        os.mkdir(itemsDirTemp)
    else:
        shutil.rmtree(itemsDirTemp)
        os.mkdir(itemsDirTemp)

    with zipfile.ZipFile(itemsBuff) as itemsZip:
        allZipPath = itemsZip.namelist()
        for path in allZipPath:
            if "/items/" in path and not (path.endswith("/")):
                itemsFileName = path.split("/items/")[1]
                with open(itemsDirTemp + itemsFileName, "wb") as file:
                    file.write(itemsZip.read(path))
    if not (os.path.isdir(itemsDir)):
        os.rename(itemsDirTemp, itemsDir)
    else:
        shutil.rmtree(itemsDir)
        os.rename(itemsDirTemp, itemsDir)


def loadDataItems(itemsDir: str) -> dict:
    items = {}
    for root, dirs, files in os.walk(itemsDir):
        for file in files:
            with open(file=(itemsDir + file), mode="r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("recipe") != None:
                items.update({file.split(".")[0]: data.get("recipe")})
            elif data.get("recipes") != None:
                items.update({file.split(".")[0]: data.get("recipes")})
    return items


def isCacheExpired(
    itemPricesPath: str, cacheDuration: timedelta = timedelta(hours=1)
) -> bool:
    if not os.path.isfile(itemPricesPath):
        return True
    mtime = os.path.getmtime(itemPricesPath)
    fileDate = datetime.fromtimestamp(mtime)
    if (datetime.now() - fileDate) > cacheDuration:
        return True
    return False


def savePrice(itemPrices: dict, itemPricesDir: str, itemPricePath: str):
    if not os.path.isdir(itemPricesDir):
        print("mkdir " + itemPricesDir)
        os.mkdir(itemPricesDir)

    with open(itemPricePath, mode="w", encoding="utf-8") as file:
        json.dump(itemPrices, file, indent=2)


def loadPrice(itemPricePath) -> dict:
    prices = {}
    with open(file=itemPricePath, mode="r", encoding="utf-8") as f:
        prices = json.load(f)
    return prices
