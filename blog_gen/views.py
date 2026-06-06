import sys
import os
import json
import time
import subprocess
import importlib
from datetime import date
import yt_dlp
import requests
from dotenv import load_dotenv
from decouple import config
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from openai import OpenAI
from .models import BlogPost, DailyGenerationCount

# Load env variables
load_dotenv()

COOKIES_FILE = os.path.join(settings.BASE_DIR, "static", "cookies", "cookies.txt")

# Config
OPENAI_API_KEY = config('OPENAI_API_KEY')
WHISPER_MODEL_NAME = config('WHISPER_MODEL', default='tiny')
_WHISPER_MODEL = None

# Quota limits for free tier usage
DURATION_CAP_SECONDS = 25 * 60  # Max 25 minutes per video
DAILY_LIMIT = 7  # Max 7 blogs per user per day

def build_ytdlp_opts(extra_opts=None):
    """Build yt-dlp options with browser-like headers to avoid YouTube blocking."""
    opts = {
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {'player_client': ['web', 'android', 'ios', 'mweb']}
        },
        'sleep_requests': 1,
        'sleep_interval': 2,
        'max_sleep_interval': 5,
    }
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
    if extra_opts:
        opts.update(extra_opts)
    return opts

# --- yt-dlp auto-update on failure ---
_LAST_YTDLP_UPDATE_ATTEMPT = 0
_UPDATE_COOLDOWN_SECONDS = 21600  # 6 hours


def _update_ytdlp_if_needed():
    """Auto-update yt-dlp if we've hit rate limits (with 6-hour cooldown)."""
    global _LAST_YTDLP_UPDATE_ATTEMPT
    now = time.time()
    if now - _LAST_YTDLP_UPDATE_ATTEMPT < _UPDATE_COOLDOWN_SECONDS:
        print("[yt-dlp] Skipping update - cooldown active")
        return False

    _LAST_YTDLP_UPDATE_ATTEMPT = now
    try:
        print("[yt-dlp] Attempting to update yt-dlp...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True, text=True, timeout=60
        )
        if "Successfully installed yt-dlp" in result.stdout:
            print("[yt-dlp] Upgrade successful, reloading module...")
            importlib.reload(yt_dlp)
            return True
        else:
            print(f"[yt-dlp] Upgrade not needed or failed: {result.stdout[-200:]}")
            return False
    except Exception as e:
        print(f"[yt-dlp] Upgrade error: {e}")
        return False


def download_audio_with_retry(link):
    """Try download once, then auto-update yt-dlp and retry on failure."""
    audio_path = download_audio(link)
    if audio_path:
        return audio_path

    print("[yt-dlp] First download attempt failed. Attempting yt-dlp update...")
    updated = _update_ytdlp_if_needed()
    if updated:
        print("[yt-dlp] Retrying download after update...")
        return download_audio(link)
    else:
        print("[yt-dlp] Could not update yt-dlp. Skipping retry.")
        return None


def get_whisper_model():
    """Load Whisper model once and keep in memory (singleton)."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        print(f"[Whisper] Loading model '{WHISPER_MODEL_NAME}' (first time - may download ~150MB)...", flush=True)
        import whisper
        _WHISPER_MODEL = whisper.load_model(WHISPER_MODEL_NAME)
        print(f"[Whisper] Model loaded successfully.", flush=True)
    return _WHISPER_MODEL

@login_required
def index(request): 
    return render(request, 'Build/index.html')

def user_login(request): 
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('/')
        else:
            request.session['error_login'] = "Invalid username or password"
            return redirect('login')
    else:
        error_login = request.session.pop('error_login', None)
        return render(request, 'Build/login.html', {'error_login': error_login})

def user_signup(request):
    if request.method == 'POST':
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password']
        repeatpassword = request.POST['repeatpassword']
        
        if password == repeatpassword:
            try:
                user = User.objects.create_user(username, email, password)
                user.save()
                login(request, user)
                return redirect('/')
            except:
                error_signup = 'Could not create account'
                return render(request, 'Build/signup.html', {'error_signup': error_signup})
        else:
            error_signup = 'Passwords do not match'
            return render(request, 'Build/signup.html', {'error_signup': error_signup})

    return render(request, 'Build/signup.html')

def user_logout(request):
    logout(request)
    return redirect('/')

@login_required
def generate_blog(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            youtubeLink = data['link']

            # Extract video metadata and subtitles in one API call (avoids rate limits)
            info = _extract_video_info(youtubeLink)
            if info is None:
                return JsonResponse({
                    'error': 'Could not fetch video metadata. The video may be unavailable or YouTube has rate-limited this session. Try again later.'
                }, status=400)

            title = info.get('title')
            duration = info.get('duration')

            # Reject videos longer than 25 minutes
            if duration is not None and duration > DURATION_CAP_SECONDS:
                return JsonResponse({
                    'error': (
                        "We're unable to process videos longer than 25 minutes "
                        "because we rely on free quotas. Please submit a shorter "
                        "video — we'd love to help!"
                    )
                }, status=400)

            # Check daily limit (max 7 blogs per day)
            allowed, counter = _check_daily_limit(request.user)
            if not allowed:
                return JsonResponse({
                    'error': (
                        "You've hit your daily limit of 7 blog generations. "
                        "Come back tomorrow — we're using free APIs and need "
                        "to share the quota fairly!"
                    )
                }, status=429)

            print(f"[generate_blog] Processing: {youtubeLink}", flush=True)
            print(f"[generate_blog] Title: {title}", flush=True)

            # Try subtitles first (fast), fall back to audio + Whisper if needed
            print(f"[generate_blog] Trying subtitles first...", flush=True)
            sub_result = get_youtube_subtitles_from_info(info)
            transcript = sub_result["text"] if sub_result else None
            transcript_lang = sub_result["lang"] if sub_result else None
            print(f"[generate_blog] Subtitle transcript length: {len(transcript) if transcript else 0}, lang: {transcript_lang}", flush=True)

            # Subtitles unavailable, fall back to audio download + Whisper (slower)
            if not transcript:
                print(f"[generate_blog] Subtitles unavailable, falling back to audio download + Whisper...", flush=True)
                audio_path = download_audio_with_retry(youtubeLink)
                print(f"[generate_blog] Audio path: {audio_path}", flush=True)
                if audio_path:
                    print(f"[generate_blog] Starting Whisper transcription...", flush=True)
                    transcript = get_transcript(audio_path)
                    transcript_lang = None  # Whisper output is auto-detected, typically mixed
                    print(f"[generate_blog] Whisper transcript length: {len(transcript) if transcript else 0}", flush=True)

            if not transcript:
                return JsonResponse({
                    'error': 'Could not extract content. Video might be private or DRM protected.'
                }, status=400)

            try:
                print(f"[generate_blog] Generating blog content...", flush=True)
                blog_content = generate_blog_content(transcript, language=transcript_lang)
                print(f"[generate_blog] Blog content generated: {len(blog_content) if blog_content else 0} chars", flush=True)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)

            if blog_content:
                title = title or "Untitled YouTube Video"

                # Increment daily counter only after successful generation
                _increment_daily_count(counter)

                return JsonResponse({'title': title, 'content': blog_content, 'link': youtubeLink}, status=200)
            else:
                return JsonResponse({'error': 'Failed to generate content'}, status=400)

        except (KeyError, json.JSONDecodeError):
            return JsonResponse({'error': 'Invalid URL Provided'}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)

def _extract_video_info(link):
    """Get video metadata and subtitles in one call (reduces rate-limit risk)."""
    try:
        ydl_opts = build_ytdlp_opts({
            'skip_download': True,
            'subtitleslangs': SUBTITLE_LANG_PRIORITY,
        })
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(link, download=False)
    except Exception as e:
        print(f"Video info extract error: {e}")
        return None


def _check_daily_limit(user):
    """Check if user has remaining daily quota (7 max). Auto-resets at midnight."""
    today = timezone.now().date()
    counter, _created = DailyGenerationCount.objects.get_or_create(
        user=user, date=today, defaults={'count': 0}
    )
    return counter.count < DAILY_LIMIT, counter


@transaction.atomic
def _increment_daily_count(counter):
    """Atomically increment daily count after successful generation."""
    locked = DailyGenerationCount.objects.select_for_update().get(pk=counter.pk)
    locked.count = F('count') + 1
    locked.save(update_fields=['count'])
    
def download_audio(link):
    try:
        ydl_opts = build_ytdlp_opts({
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(settings.MEDIA_ROOT, 'audio.%(ext)s'),
            'concurrent_fragment_downloads': 4,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '96',
            }],
        })
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
            filename = ydl.prepare_filename(info)
            # If ffmpeg post-processing changed the extension
            mp3_path = os.path.join(settings.MEDIA_ROOT, 'audio.mp3')
            if os.path.exists(mp3_path):
                return mp3_path
            return filename
    except Exception as e:
        print(f"Audio download error: {e}")
        return None

def get_transcript(audio_path):
    try:
        print(f"[Whisper] Getting model...", flush=True)
        model = get_whisper_model()
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        print(f"[Whisper] Transcribing {file_size_mb:.1f} MB audio file...", flush=True)
        result = model.transcribe(audio_path, fp16=False)
        print(f"[Whisper] Transcription complete.", flush=True)
        return result["text"]
    except Exception as e:
        print(f"[Whisper] Error: {e}", flush=True)
        return None

def _generate_with_gemini(transcript, language=None):
    """Use Gemini Flash 2.0 for blog generation (handles full transcripts in one call).
    Free tier on OpenRouter.
    """
    try:
        client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )
        lang_name = LANG_NAMES.get(language, language) if language else None

        if lang_name and language not in ('en', 'en-IN', None):
            # Non-English transcript: translate first, then write blog
            print(f"[Gemini] Non-English transcript detected ({lang_name}), translating + blogging...")
            system_prompt = (
                "You are a professional blog writer who also translates. "
                "The transcript is in {lang}. First, translate it to English. "
                "Then write a well-structured, comprehensive blog post from "
                "the English translation using Markdown with clear headings, "
                "short paragraphs, and bullet points where appropriate. "
                "Capture all key points, insights, and details. "
                "Do NOT mention it's from a video or transcript."
            ).format(lang=lang_name)
        else:
            system_prompt = (
                "You are a professional blog writer. Write a well-structured, "
                "comprehensive blog post using Markdown with clear headings, "
                "short paragraphs, and bullet points where appropriate. "
                "Capture all key points, insights, and details from the transcript. "
                "Do NOT mention it's from a video or transcript."
            )

        print(f"[Gemini] Sending full transcript ({len(transcript)} chars)...")
        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Write a detailed, comprehensive blog post from this transcript:\n\n{transcript}"}
            ],
            max_tokens=2000,
            temperature=0.7,
        )
        content = response.choices[0].message.content.strip()
        print(f"[Gemini] Success — generated {len(content)} chars")
        return content, None
    except Exception as e:
        print(f"[Gemini] Failed: {e}")
        return None, str(e)


def _generate_with_chunked_llama(transcript, language=None):
    """Fallback blog generation using chunked Llama-3-8B.
    Splits large transcripts into chunks, summarizes each, then combines.
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")

        tokens = enc.encode(transcript)
        total_tokens = len(tokens)
        print(f"[Chunked-Llama] Total transcript: {total_tokens} tokens, {len(transcript)} chars")

        lang_name = LANG_NAMES.get(language, language) if language else None
        is_non_english = lang_name and language not in ('en', 'en-IN', None)

        # 4000 tokens per chunk (safe under 8193 token limit)
        CHUNK_TOKENS = 4000
        OVERLAP_TOKENS = 200  # overlap between chunks for continuity

        if total_tokens <= 5000:
            # Fits in one go - no chunking needed
            print("[Chunked-Llama] Transcript fits in single pass")
            client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://openrouter.ai/api/v1")

            if is_non_english:
                system_msg = (
                    f"The transcript is in {lang_name}. First translate it to English, "
                    f"then write a comprehensive, well-structured blog post using Markdown "
                    f"with clear headings and short paragraphs. Don't mention it's a video."
                )
            else:
                system_msg = (
                    "You are a professional blog writer. Use Markdown, clear headings, "
                    "and short paragraphs."
                )

            response = client.chat.completions.create(
                model="meta-llama/llama-3-8b-instruct",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": f"Write a comprehensive blog post from this transcript. Don't mention it's a video:\n\n{transcript}"}
                ],
                max_tokens=800,
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()

        # --- Chunking required ---
        chunks = []
        start = 0
        while start < total_tokens:
            end = min(start + CHUNK_TOKENS, total_tokens)
            chunk_tokens = tokens[start:end]
            chunk_text = enc.decode(chunk_tokens)
            chunks.append(chunk_text)
            start += CHUNK_TOKENS - OVERLAP_TOKENS

        print(f"[Chunked-Llama] Split into {len(chunks)} chunks (~{CHUNK_TOKENS} tokens each)")

        # Step 1: Summarize each chunk
        if is_non_english:
            summary_system = (
                f"Extract all key points and important details from this {lang_name} "
                f"transcript segment. Translate them to English and present as bullet points. "
                f"Be thorough — preserve names, dates, statistics, and insights."
            )
        else:
            summary_system = (
                "Extract all key points and important details from this transcript segment. "
                "Be thorough — preserve names, dates, statistics, and insights. Use bullet points."
            )

        chunk_summaries = []
        client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://openrouter.ai/api/v1")
        for i, chunk in enumerate(chunks):
            print(f"[Chunked-Llama] Summarizing chunk {i + 1}/{len(chunks)}...")
            response = client.chat.completions.create(
                model="meta-llama/llama-3-8b-instruct",
                messages=[
                    {"role": "system", "content": summary_system},
                    {"role": "user", "content": f"Summarize the key points from this segment:\n\n{chunk}"}
                ],
                max_tokens=500,
                temperature=0.5,
            )
            chunk_summaries.append(response.choices[0].message.content.strip())

        # Step 2: Merge all chunk summaries into a final blog post
        combined_summaries = "\n\n---\n\n".join(
            f"Segment {i + 1}:\n{s}" for i, s in enumerate(chunk_summaries)
        )
        print(f"[Chunked-Llama] Merging {len(chunk_summaries)} summaries into final blog...")
        response = client.chat.completions.create(
            model="meta-llama/llama-3-8b-instruct",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional blog writer. Below are summarized segments "
                        "from a transcript. Combine them into a single, cohesive, "
                        "well-structured blog post using Markdown with clear headings, "
                        "short paragraphs, and bullet points. Do NOT mention it's a video."
                    )
                },
                {"role": "user", "content": f"Write a comprehensive blog post from these combined segment summaries:\n\n{combined_summaries}"}
            ],
            max_tokens=1500,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"[Chunked-Llama] Failed: {e}")
        raise


def generate_blog_content(transcript, language=None):
    """Generate blog from transcript using dual strategy:
    1. Try Gemini first (best quality, handles full transcript)
    2. Fall back to chunked Llama-3 if Gemini fails
    """
    # Try Gemini first (best quality)
    content, gemini_error = _generate_with_gemini(transcript, language=language)
    if content:
        return content

    # Fall back to chunked Llama-3
    print(f"[Dual-Strategy] Gemini failed ({gemini_error}), falling back to chunked Llama-3...")
    try:
        return _generate_with_chunked_llama(transcript, language=language)
    except Exception as e:
        print(f"[Dual-Strategy] Both strategies failed. Last error: {e}")
        raise Exception(f"Blog generation failed. Gemini error: {gemini_error}. Llama error: {e}")

def save_blog_post(user, title, link, content): 
    try:
        blog_post = BlogPost(user=user, y_title=title, y_link=link, gen_content=content)
        blog_post.save()
        return blog_post
    except Exception as e:
        print(f"DB Save error: {e}")
        return None

@login_required
def save_blog(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            title = data['title']
            link = data['link']
            content = data['content']
            user = request.user
            blog_post = save_blog_post(user, title, link, content)
            if blog_post:
                return JsonResponse({'message': 'Blog saved successfully', 'id': blog_post.id}, status=200)
            else:
                return JsonResponse({'error': 'Failed to save blog'}, status=500)
        except (KeyError, json.JSONDecodeError):
            return JsonResponse({'error': 'Invalid data provided'}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)

@login_required
def blog_list(request):
    blog_articles = BlogPost.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'Build/blog-list.html', {'blog_articles': blog_articles})

@login_required
def blog_details(request, i):
    blog_detail = get_object_or_404(BlogPost, id=i)
    if request.user == blog_detail.user:
        return render(request, 'Build/blog-details.html', {'blog_detail': blog_detail})
    return redirect('/')

@login_required
def delete_blog(request, i):
    if request.method == 'POST':
        blog_post = get_object_or_404(BlogPost, id=i)
        if request.user != blog_post.user:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        blog_post.delete()
        return JsonResponse({'success': True, 'message': 'Blog deleted successfully'}, status=200)
    return JsonResponse({'error': 'Invalid request method'}, status=405)

# Language priority: English first, then Hindi, then Bengali
SUBTITLE_LANG_PRIORITY = ['en', 'en-IN', 'hi', 'bn']

LANG_NAMES = {
    'en': 'English', 'en-IN': 'English (India)',
    'hi': 'Hindi', 'bn': 'Bengali',
}


# Browser-like headers to avoid Google rate-limiting on subtitle CDN
_SUBTITLE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8,bn;q=0.7',
    'Referer': 'https://www.youtube.com/',
}


def get_youtube_subtitles_from_info(info):
    """
    Fetch YouTube subtitles/auto-captions in priority order using a
    pre-fetched info dict (from _extract_video_info) to avoid duplicate
    yt-dlp API calls.
    Returns dict: {"text": "...", "lang": "hi"} or None if no captions found.
    """
    try:
        subtitles = info.get("subtitles", {})
        auto_captions = info.get("automatic_captions", {})

        # Diagnostic: what subtitles are available for this video
        print(f"[Subtitles] Manual subtitles keys: {list(subtitles.keys())}", flush=True)
        print(f"[Subtitles] Auto-captions keys:    {list(auto_captions.keys())}", flush=True)
        print(f"[Subtitles] Priority list:           {SUBTITLE_LANG_PRIORITY}", flush=True)

        # Try each language in priority order
        for lang in SUBTITLE_LANG_PRIORITY:
            sub_url = None
            captions_type = "manual" if lang in subtitles else ("auto" if lang in auto_captions else None)
            if lang in subtitles:
                sub_url = subtitles[lang][0]["url"]
            elif lang in auto_captions:
                sub_url = auto_captions[lang][0]["url"]
            else:
                continue

            print(f"[Subtitles] Found {captions_type} captions: {LANG_NAMES.get(lang, lang)}")

            # Force VTT format in the URL (YouTube sometimes returns pb3 JSON instead)
            sub_url = sub_url.replace('&fmt=srv3', '&fmt=vtt')
            sub_url = sub_url.replace('&fmt=json3', '&fmt=vtt')
            sub_url = sub_url.replace('&fmt=srv1', '&fmt=vtt')

            # Fetch with browser-like headers to avoid Google rate-limiting
            resp = requests.get(sub_url, headers=_SUBTITLE_HEADERS, timeout=15)
            response_text = resp.text

            # Check for HTML error pages (rate-limiting / 404)
            if response_text.strip().startswith('<!DOCTYPE html>') or response_text.strip().startswith('<html'):
                preview = response_text.strip()[:200].replace("\n", " ")
                print(f"[Subtitles] HTML error page returned: {preview}", flush=True)
                continue

            # ── WEBVTT format ──
            if response_text.strip().startswith("WEBVTT"):
                return {"text": strip_vtt_timestamps(response_text), "lang": lang}

            # ── pb3 / JSON protobuf format (YouTube's newer subtitle format) ──
            try:
                import json
                pb3 = json.loads(response_text)
                if isinstance(pb3, dict) and pb3.get("wireMagic") == "pb3":
                    print(f"[Subtitles] Parsing pb3 JSON format...", flush=True)
                    return {"text": strip_pb3_timestamps(pb3), "lang": lang}
            except (json.JSONDecodeError, ValueError):
                pass

            # Unknown format - skip and try next language
            preview = response_text.strip()[:200].replace("\n", " ")
            print(f"[Subtitles] Unknown response format: {preview}", flush=True)
            continue

        return None

    except Exception as e:
        print(f"Subtitle error: {e}")
        return None

def strip_vtt_timestamps(vtt):
    """Remove timestamps and metadata from WebVTT subtitle format."""
    lines = []
    for line in vtt.split("\n"):
        if ("-->" in line) or (line.strip().isdigit()) or (line.startswith("WEBVTT")):
            continue
        line = line.strip()
        if line:
            lines.append(line)
    return " ".join(lines)


def strip_pb3_timestamps(pb3):
    """Extract plain text from YouTube's pb3 (protobuf JSON) subtitle format."""
    lines = []
    for event in pb3.get("events", []):
        for seg in event.get("segs", []):
            text = seg.get("utf8", "").strip()
            if text:
                lines.append(text)
    return " ".join(lines)