from django.shortcuts import render, redirect
from django.utils import timezone
from .models import UtilityReading, TopUp, MeterConfig
from .forms import UtilityReadingForm, TopUpForm
from datetime import date, timedelta
from decimal import Decimal


def utility_home(request):
    
    reading_form = UtilityReadingForm()
    topup_form = TopUpForm()

    if request.method == 'POST':
        
        if 'submit_reading' in request.POST:
            reading_form = UtilityReadingForm(request.POST)
            if reading_form.is_valid():
                r = reading_form.save(commit=False)
                r.date = timezone.now().date()
                
                UtilityReading.objects.update_or_create(date=r.date, defaults={
                    'electricity': r.electricity,
                    'gas': r.gas
                })
                return redirect('utility_home')
        
        elif 'submit_topup' in request.POST:
            topup_form = TopUpForm(request.POST)
            if(topup_form.is_valid()):
                topup_form.save()
                return redirect('utility_home')
    
    

