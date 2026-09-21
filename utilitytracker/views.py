# utilitytracker/views.py
from django.shortcuts import render, redirect
from django.utils import timezone
from .forms import UtilityReadingForm, TopUpForm
from .models import UtilityReading, TopUp
from . import selectors, services

def utility(request):
    today_date = timezone.now().date()
    reading_form = UtilityReadingForm(initial={'date': today_date})
    topup_form = TopUpForm(initial={'date': today_date})

    if request.method == 'POST':
        # reading submit
        if 'submit_reading' in request.POST:
            date_str = request.POST.get('date')
            instance = None
            if date_str:
                try:
                    instance = UtilityReading.objects.filter(date=date_str).first()
                except Exception:
                    pass
            reading_form = UtilityReadingForm(request.POST, instance=instance)
            if reading_form.is_valid():
                r = reading_form.save(commit=False)
                services.create_or_update_reading(
                    date=r.date,
                    electricity=r.electricity,
                    gas=r.gas
                )
                return redirect('utility')

        # topup submit (create or update)
        if 'submit_topup' in request.POST:
            topup_id = request.POST.get('topup_id')
            instance = None
            if topup_id:
                try:
                    instance = TopUp.objects.filter(id=topup_id).first()
                except Exception:
                    pass
            topup_form = TopUpForm(request.POST, instance=instance)
            if topup_form.is_valid():
                topup_form.save()
                return redirect('utility')

        # topup delete
        if 'delete_topup' in request.POST:
            topup_id = request.POST.get('topup_id')
            if topup_id:
                services.delete_topup(topup_id)
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
