import sys
import os
import django
import json
import time
import yt_dlp
import requests
from dotenv import load_dotenv
from decouple import config 
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
from openai import OpenAI
from .models import BlogPost

# Load env variables
load_dotenv()

# Project path setup
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

django.setup()

from myproject.settings import BASE_DIR
COOKIES_FILE = os.path.join(BASE_DIR, "static", "cookies", "cookies.txt")

# Config
OPENAI_API_KEY = config('OPENAI_API_KEY')
WHISPER_MODEL_NAME = config('WHISPER_MODEL', default='tiny')
_WHISPER_MODEL = None

def build_ytdlp_opts(extra_opts=None):
    """
    Standard yt-dlp config to avoid DRM/Client issues.
    """
    opts = {
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {'player_client': ['web', 'android']}
        },
    }
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
    if extra_opts:
        opts.update(extra_opts)
    return opts

def get_whisper_model():
    """
    Singleton pattern to keep the model in memory.
    """
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        import whisper
        _WHISPER_MODEL = whisper.load_model(WHISPER_MODEL_NAME)
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

@csrf_exempt
def generate_blog(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            youtubeLink = data['link']
            title = yt_title(youtubeLink)
            audio_path = download_audio(youtubeLink)
            
            transcript = None
            if audio_path:
                transcript = get_transcript(audio_path)

            # Fallback to subtitles if audio transcription fails
            if not transcript:
                transcript = get_youtube_subtitles(youtubeLink)

            if not transcript:
                return JsonResponse({
                    'error': 'Could not extract content. Video might be private or DRM protected.'
                }, status=400)
            
            try:
                blog_content = generate_blog_content(transcript)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)

            if blog_content:
                title = title or "Untitled YouTube Video"
                user = request.user
                save_blog_post(user, title, youtubeLink, blog_content)

                return JsonResponse({'title': title, 'content': blog_content}, status=200)
            else:
                return JsonResponse({'error': 'Failed to generate content'}, status=400)
        
        except (KeyError, json.JSONDecodeError):
            return JsonResponse({'error': 'Invalid URL Provided'}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)

def yt_title(link):
    try:
        ydl_opts = build_ytdlp_opts({'skip_download': True})
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=False)
            return info.get('title')
    except Exception as e:
        print(f"Title fetch error: {e}")
        return None
    
def download_audio(link):
    try:
        ydl_opts = build_ytdlp_opts({
            'format': 'bestaudio[abr<=96]/bestaudio',
            'outtmpl': os.path.join(settings.MEDIA_ROOT, 'audio.%(ext)s'),
            'concurrent_fragment_downloads': 4,
        })
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
            return ydl.prepare_filename(info)
    except Exception as e:
        print(f"Audio download error: {e}")
        return None

def get_transcript(audio_path):
    try:
        model = get_whisper_model()
        result = model.transcribe(audio_path, fp16=False)
        return result["text"]
    except Exception as e:
        print(f"Whisper error: {e}")
        return None

def generate_blog_content(transcript):
    try:
        client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )
        response = client.chat.completions.create(
            model="meta-llama/llama-3-8b-instruct",
            messages=[
                {"role": "system", "content": "You are a professional blog writer. Use Markdown, clear headings, and short paragraphs."},
                {"role": "user", "content": f"Write a comprehensive blog post from this transcript. Don't mention it's a video:\n\n{transcript}"}
            ],
            max_tokens=800,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"LLM Error: {e}")
        raise 

def save_blog_post(user, title, link, content): 
    try:
        blog_post = BlogPost(user=user, y_title=title, y_link=link, gen_content=content)
        blog_post.save()
        return blog_post
    except Exception as e:
        print(f"DB Save error: {e}")
        return None

def blog_list(request):
    blog_articles = BlogPost.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'Build/blog-list.html', {'blog_articles': blog_articles})

def blog_details(request, i):
    blog_detail = BlogPost.objects.get(id=i)
    if request.user == blog_detail.user:
        return render(request, 'Build/blog-details.html', {'blog_detail': blog_detail})
    else:
        return redirect('/')

def get_youtube_subtitles(link):
    try:
        ydl_opts = build_ytdlp_opts({
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['en'],
        })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=False)
            
            if info.get("subtitles", {}).get("en"):
                sub_url = info["subtitles"]["en"][0]["url"]
            elif info.get("automatic_captions", {}).get("en"):
                sub_url = info["automatic_captions"]["en"][0]["url"]
            else:
                return None

        vtt_content = requests.get(sub_url).text
        return strip_vtt_timestamps(vtt_content)
    except Exception as e:
        print(f"Subtitle error: {e}")
        return None

def strip_vtt_timestamps(vtt):
    """
    Cleans WebVTT formatting to get raw text.
    """
    lines = []
    for line in vtt.split("\n"):
        if ("-->" in line) or (line.strip().isdigit()) or (line.startswith("WEBVTT")):
            continue
        line = line.strip()
        if line:
            lines.append(line)
    return " ".join(lines)