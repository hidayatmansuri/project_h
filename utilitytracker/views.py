# utilitytracker/views.py
from django.shortcuts import render, redirect
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal, InvalidOperation
from .models import UtilityReading, TopUp
from .forms import UtilityReadingForm, TopUpForm
import json

def utility(request):
    reading_form = UtilityReadingForm()
    topup_form = TopUpForm()

    if request.method == 'POST':
        # reading submit
        if 'submit_reading' in request.POST:
            reading_form = UtilityReadingForm(request.POST)
            if reading_form.is_valid():
                r = reading_form.save(commit=False)
                r.date = timezone.now().date()
                # update or create -> one entry per date
                UtilityReading.objects.update_or_create(
                    date=r.date,
                    defaults={'electricity': r.electricity, 'gas': r.gas}
                )
                return redirect('utility')

        # topup submit
        if 'submit_topup' in request.POST:
            topup_form = TopUpForm(request.POST)
            if topup_form.is_valid():
                topup_form.save()
                return redirect('utility')

    # --- gather data ---
    readings_qs = UtilityReading.objects.all().order_by('date')  # ascending
    readings = list(readings_qs)
    topups_qs = TopUp.objects.all().order_by('date')  # ascending
    topups = list(topups_qs)

    # helper: group topups by date (date portion) and also get topups between two dates inclusive
    topups_by_date = {}
    for t in topups:
        d = t.date.date()
        topups_by_date.setdefault(d, []).append(t)

    # Prepare arrays for charting: dates, elec_usage, gas_usage, and arrays of readings to display
    chart_dates = []
    elec_usage = []
    gas_usage = []
    elec_readings = []  # the raw meter reading at each date (for display)
    gas_readings = []

    # We compute usage for each consecutive pair: prev -> current
    prev = None
    for r in readings:
        if prev is None:
            # can't compute usage for first reading (no previous) — we still store the reading
            prev = r
            chart_dates.append(r.date.isoformat())
            elec_readings.append(float(r.electricity) if r.electricity is not None else None)
            gas_readings.append(float(r.gas) if r.gas is not None else None)
            # usage is 0 for first point (so chart line shows 0 or no bar) — we append 0 to keep arrays equal
            elec_usage.append(0.0)
            gas_usage.append(0.0)
            continue

        # compute top-ups that happened strictly between prev.date (exclusive) and r.date (inclusive)
        # We include topups on the current date (they increase reading before measuring usage)
        start_dt = prev.date
        end_dt = r.date
        # sum topups amounts between dates
        elec_topups_sum = Decimal('0.00')
        gas_topups_sum = Decimal('0.00')
        for t in topups:
            t_date = t.date.date()
            if start_dt < t_date <= end_dt:
                if t.meter == 'electricity':
                    elec_topups_sum += Decimal(t.amount)
                elif t.meter == 'gas':
                    gas_topups_sum += Decimal(t.amount)

        # default to 0 if readings missing
        eu = 0.0
        gu = 0.0

        # electricity usage = prev.electricity - (current.electricity - elec_topups_sum)
        if prev.electricity is not None and r.electricity is not None:
            try:
                eu_calc = (Decimal(prev.electricity) - (Decimal(r.electricity) - elec_topups_sum))
                # if negative (shouldn't happen if data sane), set 0
                eu = float(eu_calc) if eu_calc > 0 else 0.0
            except (InvalidOperation, TypeError):
                eu = 0.0

        # gas usage similar
        if prev.gas is not None and r.gas is not None:
            try:
                gu_calc = (Decimal(prev.gas) - (Decimal(r.gas) - gas_topups_sum))
                gu = float(gu_calc) if gu_calc > 0 else 0.0
            except (InvalidOperation, TypeError):
                gu = 0.0

        # Append current date and usage
        chart_dates.append(r.date.isoformat())
        elec_usage.append(round(eu, 2))
        gas_usage.append(round(gu, 2))
        elec_readings.append(float(r.electricity) if r.electricity is not None else None)
        gas_readings.append(float(r.gas) if r.gas is not None else None)

        prev = r

    # Last 30 days readings (aligned dates row) — create list of last 30 dates and map readings if present
    today = timezone.now().date()
    last_30_dates = [today - timedelta(days=i) for i in reversed(range(30))]  # oldest -> newest
    readings_map = {r.date: r for r in readings}

    last_30_rows = []
    for d in reversed(last_30_dates):
        r = readings_map.get(d)
        if r and (r.electricity is not None or r.gas is not None):
            last_30_rows.append({
                'date': d.isoformat(),
                'electricity': float(r.electricity) if (r and r.electricity is not None) else None,
                'gas': float(r.gas) if (r and r.gas is not None) else None,
            })

    # Top-ups table (most recent first)
    recent_topups = TopUp.objects.all().order_by('-date')[:50]

    # Chart payload (daily arrays)
    chart_payload = {
        'dates': chart_dates,
        'elec_usage': elec_usage,
        'gas_usage': gas_usage,
        'elec_readings': elec_readings,
        'gas_readings': gas_readings,
        'topups': [
            {'date': t.date.isoformat(), 'meter': t.meter, 'amount': float(t.amount), 'note': t.note}
            for t in recent_topups
        ]
    }

    context = {
        'reading_form': reading_form,
        'topup_form': topup_form,
        'chart_payload': chart_payload,
        'last_30_rows': last_30_rows,
        'recent_topups': recent_topups,
    }
    return render(request, 'utility_home.html', context)
