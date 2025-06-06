from django.shortcuts import render
from django.http import HttpResponse
from django.template import loader

def home(request):
    return HttpResponse ("Welcome HOME")


# Create your views here.
