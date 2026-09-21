from django.shortcuts import render
from utilitytracker.models import UtilityReading #import Reading amount from Utilitytracker Models

# Create your views here.
def home(request):
    #get latest TopUp amount for electricity
    electricity = UtilityReading.objects.filter(electricity__isnull=False).order_by('-date').first()
    #get latest TopUp amount for gas
    gas = UtilityReading.objects.filter(gas__isnull=False).order_by('-date').first()
    return render(request, 'home.html',{
        'electricity': electricity,
        'gas': gas
    })

