# utilitytracker/views.py
from django.shortcuts import render, redirect
from django.utils import timezone
from .forms import UtilityReadingForm, TopUpForm
from . import selectors, services

def utility(request):
    today_date = timezone.now().date()
    reading_form = UtilityReadingForm(initial={'date': today_date})
    topup_form = TopUpForm(initial={'date': today_date})

    if request.method == 'POST':
        # reading submit
        if 'submit_reading' in request.POST:
            reading_form = UtilityReadingForm(request.POST)
            if reading_form.is_valid():
                r = reading_form.save(commit=False)
                services.create_or_update_reading(
                    date=r.date,
                    electricity=r.electricity,
                    gas=r.gas
                )
                return redirect('utility')

        # topup submit
        if 'submit_topup' in request.POST:
            topup_form = TopUpForm(request.POST)
            if topup_form.is_valid():
                topup_form.save()
                return redirect('utility')

    # --- gather data using selectors ---
    chart_payload = selectors.get_utility_data_for_charts()
    last_30_rows, last_30_dates = selectors.get_last_30_days_readings()
    recent_topups = selectors.get_recent_topups()

    context = {
        'reading_form': reading_form,
        'topup_form': topup_form,
        'chart_payload': chart_payload,
        'last_30_rows': last_30_rows,
        'last_30_dates': [d.isoformat() for d in last_30_dates],
        'recent_topups': recent_topups,
    }
    return render(request, 'utility_home.html', context)
