from django.shortcuts import render
from .models import PersonalInfo, Qualification, Experience

# Create your views here.

def cv(request):
    personal_info = PersonalInfo.objects.all()
    qualification = Qualification.objects.all().order_by('-start_date')
    experience = Experience.objects.all().order_by('-start_date')
    return render(request,'cv.html', {
        'personal_info': personal_info,
        'qualification': qualification,
        'experience': experience,
    })
