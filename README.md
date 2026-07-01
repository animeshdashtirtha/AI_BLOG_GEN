# AI_BLOG_GEN

![Python](https://img.shields.io/badge/Python-3.11-blue) ![Django](https://img.shields.io/badge/Django-5.2.5-green)

Convert YouTube transcripts into blog-style posts quickly. This README lists only the features implemented in the codebase.

Implemented features

- Transcript-to-blog generation: uses subtitles or Whisper transcription when needed.
- Dual generation strategy: OpenRouter/Gemini primary, Llama-based chunked fallback.
- User auth: sign up, login, logout (Django auth).
- Save & manage posts: create, list, view, and delete saved posts (`BlogPost` model).
- Daily quota: per-user daily generation tracking via `DailyGenerationCount` (default 7/day).
- Audio & subtitle handling: `yt-dlp` for subtitles/audio and Whisper for transcription.
- Admin: `BlogPost` registered in Django admin.
- Env config: reads `OPENAI_API_KEY`, `WHISPER_MODEL`, and uses `MEDIA_ROOT` for audio files.

Quick start

```bash
python -m venv myenv
myenv\Scripts\activate
pip install -r requirements.txt
# add .env with Your OPENAI_API_KEY
python manage.py migrate
python manage.py runserver
```

Usage

- Provide a YouTube link; the app extracts subtitles or audio and generates a blog draft.
- Save generated posts to your account and manage them via the UI.

Configuration

- Set `OPENAI_API_KEY` and optional `WHISPER_MODEL` in your environment.
- Ensure `MEDIA_ROOT` is writable for temporary audio files.

Project structure (high level)

- `blog_gen/` — app models, views, and generation logic
- `myproject/` — Django settings and URL configuration
- `templates/`, `static/`, `media/` — frontend assets and storage

Contributing

- Fork, branch, and open a PR. Keep changes focused.

License

See the `LICENSE` file if present.

Getting Started

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

Usage

- Upload or provide a YouTube transcript to the app.
- Choose generation options (concise, detailed, or custom tone).
- Generate a blog draft, review, and edit as needed.

Configuration

- Store API keys in a `.env` file (do not commit this file).
- Settings to check: `OPENAI_API_KEY`, `DJANGO_SECRET_KEY`, and media/static paths.

Project Structure

- `blog_gen/` — main app with models, views, and generation logic
- `myproject/` — Django project settings and URL config
- `templates/` & `static/` — front-end templates and assets

Contributing

- Fork the repo, create a feature branch, and open a PR.
- Please run style checks and keep changes focused and minimal.

License

This project is provided under the MIT License. See the `LICENSE` file for details.

Contact

If you have questions or want help integrating this into a project, open an issue or contact the maintainer.
