import base64
import random
from pathlib import Path

import requests
import pandas as pd

URL = "http://192.168.0.110:8095/api/conversations/71/chat"
IMAGES_DIR = Path(__file__).parent / "images"
OUTPUT_CSV = Path(__file__).parent / "labels.csv"


def get_mime_type(filepath):
    ext = filepath.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(ext, "image/jpeg")


def label_image(filepath):
    with open(filepath, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    mime = get_mime_type(filepath)
    data_url = f"data:{mime};base64,{b64}"

    payload = {
        "message": "What is in this image?",
        "attachments": [
            {
                "name": filepath.name,
                "kind": "image",
                "mime": mime,
                "data_url": data_url,
            }
        ],
    }

    response = requests.post(URL, json=payload, timeout=120).json()
    return response["response"]


def main():
    image_files = [
        p for p in IMAGES_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
    ]
    random.shuffle(image_files)

    df = pd.DataFrame(columns=["input", "output"])

    for i, img_path in enumerate(image_files, 1):
        try:
            output = label_image(img_path)
        except Exception as e:
            print(f"  Error: {e}")
            output = f"ERROR: {e}"

        print(f"[{i}/{len(image_files)}] Processing {img_path.name}..." + str(output))


        df.loc[len(df)] = {"input": f"images/{img_path.name}", "output": output}
        df.to_csv(OUTPUT_CSV, index=False)

    print(f"Done. Results saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
