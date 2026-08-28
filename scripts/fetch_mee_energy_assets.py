from pathlib import Path
from urllib.request import Request, urlopen

FILES = {
    "mee-009.jpg": "https://archives.bulbagarden.net/media/upload/2/20/BasicGrassEnergyMEEEnergy9.jpg",
    "mee-010.jpg": "https://archives.bulbagarden.net/media/upload/7/71/BasicFireEnergyMEEEnergy10.jpg",
    "mee-011.jpg": "https://archives.bulbagarden.net/media/upload/3/3d/BasicWaterEnergyMEEEnergy11.jpg",
    "mee-012.jpg": "https://archives.bulbagarden.net/media/upload/1/10/BasicLightningEnergyMEEEnergy12.jpg",
    "mee-013.jpg": "https://archives.bulbagarden.net/media/upload/3/33/BasicPsychicEnergyMEEEnergy13.jpg",
    "mee-014.jpg": "https://archives.bulbagarden.net/media/upload/8/8c/BasicFightingEnergyMEEEnergy14.jpg",
    "mee-015.jpg": "https://archives.bulbagarden.net/media/upload/f/f8/BasicDarknessEnergyMEEEnergy15.jpg",
    "mee-016.jpg": "https://archives.bulbagarden.net/media/upload/9/9a/BasicMetalEnergyMEEEnergy16.jpg",
}

DEST = Path("assets/energies")
DEST.mkdir(parents=True, exist_ok=True)

headers = {
    "User-Agent": "Cardoryx/2.1.27 GitHub Actions asset fetcher"
}

for filename, url in FILES.items():
    print(f"Downloading {filename}...")

    request = Request(url, headers=headers)

    with urlopen(request, timeout=60) as response:
        data = response.read()
        content_type = response.headers.get("Content-Type", "")

    if "image" not in content_type.lower():
        raise RuntimeError(
            f"{filename}: unexpected Content-Type {content_type!r}"
        )

    if len(data) < 50_000:
        raise RuntimeError(
            f"{filename}: downloaded file is unexpectedly small ({len(data)} bytes)"
        )

    (DEST / filename).write_bytes(data)
    print(f"Saved {filename}: {len(data)} bytes")

print("All MEE009-MEE016 energy assets downloaded successfully.")
