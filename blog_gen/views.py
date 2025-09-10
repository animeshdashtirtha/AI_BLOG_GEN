import sys
import os
import django
from dotenv import load_dotenv
load_dotenv()
from decouple import config 
from django.shortcuts import render
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
import time
import yt_dlp
from django.conf import settings
from openai import OpenAI
from .models import BlogPost
from myproject.settings import BASE_DIR


# Add project root to Python path (optional, but safe)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
# Initialize Django
django.setup()
# Import BASE_DIR and build path ---
from myproject.settings import BASE_DIR
COOKIES_FILE = os.path.join(BASE_DIR, "static", "cookies", "cookies.txt")

# openaitoken
OPENAI_API_KEY = config('OPENAI_API_KEY')

@login_required
def index (request): 
   return render(request, 'Build/index.html')


def user_login (request): 
   if request.method=='POST':
      username= request.POST['username']
      password= request.POST['password']

      user=authenticate(request, username=username, password=password)
      if user is not None:
        login(request, user)
        return redirect('/')
      else:
        request.session['error_login'] = "Invalid username or password"
        return redirect('login')
   else:
      error_login = request.session.pop('error_login', None)
      return render(request, 'Build/login.html', {'error_login': error_login})




def user_signup (request):
   
   if request.method=='POST':
      username= request.POST['username']
      email= request.POST['email']
      password= request.POST['password']
      repeatpassword= request.POST['repeatpassword']
      
      if password==repeatpassword:
            try:
                user= User.objects.create_user(username, email, password)
                user.save()
                login(request, user)
                return redirect('/')
            except:
                error_signup= 'Could not create account'
                return render(request, 'Build/signup.html', {'error_signup':error_signup} )
      else:
         error_signup='password do not match'
         return render(request, 'Build/signup.html', {'error_signup':error_signup} )

   return render(request, 'Build/signup.html')



def user_logout (request):
   logout(request)
   return redirect('/')


@csrf_exempt
def generate_blog (request):
   if request.method == 'POST':
      try:
         data = json.loads(request.body)
         youtubeLink = data['link']
         title = yt_title(youtubeLink)
         audio_path=download_audio(youtubeLink)
         if not audio_path:
            return JsonResponse({'error': 'Audio download failed'}, status=500)
         
         transcript = get_transcript(audio_path)
         
         try:
            blog_content = generate_blog_content(transcript)
         except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

         if title and blog_content:
            # save blog to database
            user = request.user
            blog_post = save_blog_post(user, title, youtubeLink, blog_content)

            # sending data to frontend
            return JsonResponse({'title': title,'content': blog_content}, status=200)
         else:
            return JsonResponse({'error': 'Could not complete request'}, status=400)
      
         
        

      except (KeyError, json.JSONDecodeError):
         return JsonResponse({'error': 'Invalid URL Provided'}, status=400)
   else:
      return JsonResponse({'error': 'Invalid request method'}, status=405)
      

def yt_title(link):
   try:
      ydl_opts = {
         'cookies': 'COOKIES_FILE',
      }
      with yt_dlp.YoutubeDL(ydl_opts) as ydl:
         info = ydl.extract_info(link, download=False)
         return info.get('title')
   except Exception as e:
      print(f"Error fetching YouTube title: {e}")
      return None
    
def download_audio(link):
   try:
      ydl_opts = {
         'format': 'bestaudio/best',
         'outtmpl': os.path.join(settings.MEDIA_ROOT, 'audio.%(ext)s'),
         'cookies': 'COOKIES_FILE',
         'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
         }],
         'quiet': True
      }
      with yt_dlp.YoutubeDL(ydl_opts) as ydl:
         info = ydl.extract_info(link, download=True)
         return ydl.prepare_filename(info).rsplit('.', 1)[0] + '.mp3'
   except Exception as e:
      print(f"Error downloading audio: {e}")
      return None


def get_transcript(audio_path):
   import whisper
   try:
      # Load the Whisper model (choose: tiny, base, small, medium, large)
      model = whisper.load_model("base")
      # Transcribe the audio file
      result = model.transcribe(audio_path)
      # Return the transcript text
      return result["text"]
   except Exception as e:
      print(f"Error during transcription: {e}")
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
            {"role": "system", "content": ("You are a professional blog writer. Write engaging, human-like articles with clear structure. "
               "Use an introduction, multiple sections with headings, short paragraphs, and a conclusion. "
               "Add bullet points or numbered lists if relevant. Use Markdown formatting for headings and lists.")},
            {"role": "user", "content": f"Generate a comprehensive blog post based on the following transcript. Do not make it look like a YouTube video:\n\n{transcript}"}
         ],
         max_tokens=800,
         temperature=0.7,
      )
      generated_text = response.choices[0].message.content.strip()
      return generated_text
   except Exception as e:
      print(f"Error generating blog content: {e}")
      raise  # This will propagate the exception to the caller
    

def save_blog_post(user, title, link, content): 
    try:
        blog_post = BlogPost(user=user, y_title=title, y_link=link, gen_content=content)
        blog_post.save()
        return blog_post
    except Exception as e:
        print(f"Error saving blog post: {e}")
        return None
    

  
   #  watch blog list in frontend

def blog_list(request):
   blog_articles= BlogPost.objects.filter(user=request.user).order_by('-created_at')
   return render(request, 'Build/blog-list.html', {'blog_articles': blog_articles})
   

def blog_details(request, i):
   blog_detail = BlogPost.objects.get(id=i)
   if request.user == blog_detail.user:
      return render(request, 'Build/blog-details.html', {'blog_detail': blog_detail})
   else:
      return redirect('/')
   
