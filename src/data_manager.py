import requests, io, zipfile, os, shutil, json


def loadData():

    headers = {"Accept": "application/vnd.github+json"}
    OWNER = "NotEnoughUpdates"
    REPO = "NotEnoughUpdates-REPO"
    EXT = "zip"
    REF = "master"

    eTag = ""
    eTagDir = "data/"
    eTagFileName = "eTag.txt"
    if os.path.isfile(eTagDir + eTagFileName):
        with open(file=(eTagDir + eTagFileName), mode="r", encoding="utf-8") as file:
            eTag = file.read()
            headers.update({"If-None-Match": eTag})

    url = f"https://api.github.com/repos/{OWNER}/{REPO}/{EXT}ball/{REF}"
    r = requests.get(url, headers=headers)
    print(r.status_code)
    itemsDir = "data/items/"
    itemDirTemp = "data/items_temp/"
    if r.status_code == 304:
        print("No Updates")
    elif r.status_code == 200:
        print("Load Updates")

        itemsBuff = io.BytesIO(r.content)

        if not (os.path.isdir(itemDirTemp)):
            os.mkdir(itemDirTemp)
        else:
            shutil.rmtree(itemDirTemp)
            os.mkdir(itemDirTemp)

        with zipfile.ZipFile(itemsBuff) as itemsZip:
            allZipPath = itemsZip.namelist()
            for path in allZipPath:
                if "/items/" in path and not (path.endswith("/")):
                    itemsFileName = path.split("/items/")[1]
                    with open(itemDirTemp + itemsFileName, "wb") as file:
                        file.write(itemsZip.read(path))
        if not (os.path.isdir(itemsDir)):
            os.rename(itemDirTemp, itemsDir)
        else:
            shutil.rmtree(itemsDir)
            os.rename(itemDirTemp, itemsDir)

        with open(file=(eTagDir + eTagFileName), mode="w", encoding="utf-8") as file:
            file.write(r.headers.get("ETag"))
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
