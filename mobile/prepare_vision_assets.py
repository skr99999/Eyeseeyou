"""Prepare the pinned MediaPipe Web runtime and models for the mobile build."""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import tarfile
from urllib.request import urlopen


ASSETS = Path(__file__).resolve().parent / "web" / "vision-assets"
NPM_URL = "https://registry.npmjs.org/@mediapipe/tasks-vision/-/tasks-vision-0.10.32.tgz"
NPM_SHA256 = "b362a2b56aafcce7857047c25dc8fd69612fd8e75018e264717d24290e7815c1"
RUNTIME = {
    "vision_bundle.js": "de83c48ff329717a27aeb528d5ef5f47f077c628a5302dc483aca5b513e7464b",
    "wasm/vision_wasm_internal.js": "6f6b86509cf9e163ea1cfec7edc8cf53732699c04781e4c21c557c1ba402310e",
    "wasm/vision_wasm_internal.wasm": "cb3ec20026a9aecc2a81a93c25630ceb5389297ddb7a5f0bd61dd09cde606b9b",
    "wasm/vision_wasm_nosimd_internal.js": "9f8fc960e363f0fb2f42f7937b97ae9cf9a5630490f71031fa90caa9bb121938",
    "wasm/vision_wasm_nosimd_internal.wasm": "924274fcd5ac8985f6570a8573e7971b7bd2d580ba1b8f3beb0ba8f95db6347c",
}
MODELS = {
    "face_landmarker": "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
    "gesture_recognizer": "97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482",
}


def download(url):
    with urlopen(url, timeout=60) as response:
        return response.read()


def matches(path, expected):
    return path.is_file() and sha256(path.read_bytes()).hexdigest() == expected


def write_checked(path, data, expected):
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Unexpected SHA-256 for {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def prepare():
    if not all(matches(ASSETS / name, digest) for name, digest in RUNTIME.items()):
        data = download(NPM_URL)
        if sha256(data).hexdigest() != NPM_SHA256:
            raise ValueError("Unexpected SHA-256 for the MediaPipe npm archive")
        with tarfile.open(fileobj=BytesIO(data), mode="r:gz") as archive:
            for name, digest in RUNTIME.items():
                member = "vision_bundle.mjs" if name == "vision_bundle.js" else name
                with archive.extractfile(f"package/{member}") as source:
                    write_checked(ASSETS / name, source.read(), digest)

    for name, digest in MODELS.items():
        path = ASSETS / f"{name}.task"
        if not matches(path, digest):
            url = f"https://storage.googleapis.com/mediapipe-models/{name}/{name}/float16/1/{name}.task"
            write_checked(path, download(url), digest)


if __name__ == "__main__":
    prepare()
    print(f"Verified MediaPipe assets in {ASSETS}")
