from django.shortcuts import render
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required


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
          error_login="Invalid username or password"
          return render(request, 'Build/login.html', {'error_login':error_login})
   return render(request, 'Build/login.html')



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

def generate_blog (request):
    pass