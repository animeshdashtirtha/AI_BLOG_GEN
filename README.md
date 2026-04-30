# AI_BLOG_GEN

Simple Django app to generate blog-style posts from YouTube transcripts.
Instead of watching a long video just read the SUMMERY and save time.

Quick start

1. Create a virtual environment and activate it.

```bash
python -m venv myenv
myenv\Scripts\activate
```

2. Install dependencies and configure environment.

```bash
pip install -r requirements.txt
# Create a .env file and set your API key variable as OPENAI_API_KEY
```

3. Run migrations and start the development server.

```bash
python manage.py migrate
python manage.py runserver
```

Notes

- Do not commit the `.env` file or your virtual environment.
- This repository is intended for demonstration and local development.
