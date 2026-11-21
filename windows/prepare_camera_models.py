"""Prepare versioned Google MediaPipe model bundles for the Windows desktop app."""

from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen
import os
from tempfile import NamedTemporaryFile


MODELS = {
    "face_landmarker": "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
    "gesture_recognizer": "97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482",
}


def prepare():
    folder = Path(os.environ["LOCALAPPDATA"]) / "EyeSeeYou Edge" / "models"
    folder.mkdir(parents=True, exist_ok=True)
    for name, digest in MODELS.items():
        target = folder / (name + ".task")
        if target.is_file() and sha256(target.read_bytes()).hexdigest() == digest:
            continue
        url = f"https://storage.googleapis.com/mediapipe-models/{name}/{name}/float16/1/{name}.task"
        with urlopen(url, timeout=60) as response:
            data = response.read()
        if sha256(data).hexdigest() != digest:
            raise ValueError(f"Unexpected SHA-256 for {name}")
        with NamedTemporaryFile(dir=folder, delete=False) as cache:
            cache.write(data)
        Path(cache.name).replace(target)
    return folder


if __name__ == "__main__":
    print(prepare())
