from django.shortcuts import render
from django.http import HttpResponse
from django.template import loader

def cv(request):
    return HttpResponse ("Welcome to my CV")

# Create your views here.
