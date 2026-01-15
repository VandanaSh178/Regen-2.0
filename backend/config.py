from dotenv import load_dotenv
load_dotenv()   # 👈 loads .env file

import os

API_TOKEN = os.getenv("PLATE_RECOGNIZER_TOKEN")

API_URL = "https://api.platerecognizer.com/v1/plate-reader/"
CAMERA_INDEX = 0
LOG_FILE = "logs.csv"
API_INTERVAL = 3

BLACKLIST = ["DL8CAF5030", "MH12AB1234"]
