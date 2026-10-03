import requests


class HypixelClient:
    BASE_URL = "https://api.hypixel.net/v2"

    def __init__(self, apiKey: str):
        self.session = requests.Session()
        self.session.headers.update({"API-Key": apiKey})

    def _makeRequest(self, endpoint: str) -> dict:
        url = f"{self.BASE_URL}/{endpoint}"
        try:
            r = self.session.get(url)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            print(f"Error requesting {url}: {e}")
            return {}

    def getBazaarPrices(self):
        return self._makeRequest("skyblock/bazaar")

    def getSkyblockItems(self):
        return self._makeRequest("resources/skyblock/items")


def fetchItems(eTag: str) -> tuple[bytes | None, str | None]:
    headers = {"Accept": "application/vnd.github+json", "If-None-Match": eTag}
    OWNER = "NotEnoughUpdates"
    REPO = "NotEnoughUpdates-REPO"
    EXT = "zip"
    REF = "master"
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/{EXT}ball/{REF}"
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            newETag = r.headers.get("ETag")
            return r.content, newETag
        elif r.status_code == 304:
            return None, eTag
    except requests.RequestException as e:
        print(f"Error with fetch Data from: {url}, Error: {e}")
        return None, None


def fetchAhPrices(findItem: str, skyCoflToken: str) -> dict:
    url = f"https://sky.coflnet.com/api/item/price/{findItem}"
    headers = {"Authorization": f"Bearer {skyCoflToken}"}
    filters = {"Clean": "yes"}
    try:
        r = requests.get(url, headers=headers, params=filters)
        return r.json()
    except requests.RequestException as e:
        print(f"Error with API, url: {url}, for item: {findItem}: {e}")
        return {}
