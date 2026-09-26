import requests
import io
import zipfile
import os
import shutil

headers = {"Accept": "application/vnd.github+json"}
OWNER = "NotEnoughUpdates"
REPO = "NotEnoughUpdates-REPO"
EXT = "zip"
REF = "master"

url = f"https://api.github.com/repos/{OWNER}/{REPO}/{EXT}ball/{REF}"
r = requests.get(url, headers=headers)
print(r.status_code)
itemsBuff = io.BytesIO(r.content)
itemDirTemp = "data/items_temp/"
itemsDir = "data/items/"
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
