import os
import sys
import yt_dlp
import django
from django.conf import settings
from decouple import config 


# Add the project root directory to Python path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()


def yt_title(link):
   try:
      ydl_opts = {
         'cookies': config('YOUTUBE_COOKIES_FILE'),
         'verbose': True, 
      }
      with yt_dlp.YoutubeDL(ydl_opts) as ydl:
         info = ydl.extract_info(link, download=False)
         return print(info.get('title'))
   except Exception as e:
      print(f"Error fetching YouTube title: {e}")
      return print(e)
   
# def download_audio(link):
#    try:
#       ydl_opts = {
#          'format': 'bestaudio/best',
#          'outtmpl': os.path.join(settings.MEDIA_ROOT, 'audio.%(ext)s'),
#          'cookies': config('YOUTUBE_COOKIES_FILE'),
#          'postprocessors': [{
#             'key': 'FFmpegExtractAudio',
#             'preferredcodec': 'mp3',
#             'preferredquality': '192',
#          }],
#          'quiet': True
#       }
#       with yt_dlp.YoutubeDL(ydl_opts) as ydl:
#          info = ydl.extract_info(link, download=True)
#          return ydl.prepare_filename(info).rsplit('.', 1)[0] + '.mp3'
#    except Exception as e:
#       print(f"Error downloading audio: {e}")
#       return None

link = "https://www.youtube.com/watch?v=b2i1IiUDTRs&rco=1"
yt_title(link)
# download_audio(link)