import os
import sys
import django
from django.conf import settings

# Add project root to Python path (optional, but safe)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

# Initialize Django
django.setup()

# --- Step 2: Import BASE_DIR and build path ---
from myproject.settings import BASE_DIR

COOKIES_FILE = os.path.join(BASE_DIR, "static", "cookies", "cookies.txt")
print("Cookies path:", COOKIES_FILE)

with open(COOKIES_FILE, "r", encoding="utf-8") as f:
        data = f.read()
        print("cookies content:\n", data)
      