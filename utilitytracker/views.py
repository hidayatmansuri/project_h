# utilitytracker/views.py
from django.shortcuts import render, redirect
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal, InvalidOperation
from .models import UtilityReading, TopUp
from .forms import UtilityReadingForm, TopUpForm
from collections import defaultdict
import json

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

    # Last 30 days only on Graph
    today = timezone.now().date()
    cutoff = today - timedelta(days=30)
    readings_30 = [r for r in readings if r.date >= cutoff]
    
    # Prepare arrays for charting: dates, elec_usage, gas_usage, and arrays of readings to display
    chart_dates = []
    elec_usage = []
    gas_usage = []
    elec_readings = []  # the raw meter reading at each date (for display)
    gas_readings = []
    
    for r in readings_30:
        chart_dates.append(r.date.isoformat())
        elec_readings.append(float(r.electricity) if r.electricity is not None else None)
        gas_readings.append(float(r.gas) if r.gas is not None else None)

    # We compute usage for each consecutive pair: prev -> current
    prev = None
    for r in readings_30:
        if prev is None:
            # can't compute usage for first reading (no previous) — we still store the reading
            elec_usage.append(0.0)
            gas_usage.append(0.0)
            prev = r
            continue
            # chart_dates.append(r.date.isoformat())
            # elec_readings.append(float(r.electricity) if r.electricity is not None else None)
            # gas_readings.append(float(r.gas) if r.gas is not None else None)
            # usage is 0 for first point (so chart line shows 0 or no bar) — we append 0 to keep arrays equal
            # elec_usage.append(0.0)
            # gas_usage.append(0.0)
            # continue

        # compute top-ups that happened strictly between prev.date (exclusive) and r.date (inclusive)
        # We include topups on the current date (they increase reading before measuring usage)
        #start_dt = prev.date
        #end_dt = r.date
        # sum topups amounts between dates
        elec_topups_sum = Decimal('0.00')
        gas_topups_sum = Decimal('0.00')
        for t in topups:
            t_date = t.date.date()
            #if start_dt < t_date <= end_dt:
            if prev.date < t_date <= r.date:
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
        #chart_dates.append(r.date.isoformat())
        elec_usage.append(round(eu, 2))
        gas_usage.append(round(gu, 2))
        #elec_readings.append(float(r.electricity) if r.electricity is not None else None)
        #gas_readings.append(float(r.gas) if r.gas is not None else None)
        prev = r
    
    elec_balance = []
    gas_balance = []
    balance_e = 0.0
    balance_g = 0.0

    for i, d_str in enumerate(chart_dates):
        d = date.fromisoformat(d_str)

        # Add top-ups that occurred on this date
        for t in topups_by_date.get(d, []):
            if t.meter == 'electricity':
                balance_e += float(t.amount)
            elif t.meter == 'gas':
                balance_g += float(t.amount)

        # Subtract consumption for this date
        balance_e -= elec_usage[i]
        balance_g -= gas_usage[i]

        elec_balance.append(round(balance_e, 2))
        gas_balance.append(round(balance_g, 2))

    # Monthly Aggregate
    monthly_usage = defaultdict(lambda: {'elec':0.0, 'gas':0.0})
    yearly_usage = defaultdict(lambda: {'elec':0.0, 'gas':0.0})
    for i, d in enumerate(chart_dates):
        month_key = d[:7]  # YYYY-MM
        year_key = d[:4]  # YYYY
    monthly_usage[month_key]['elec'] += elec_usage[i]
    monthly_usage[month_key]['gas'] += gas_usage[i]
    yearly_usage[year_key]['elec'] += elec_usage[i]
    yearly_usage[year_key]['gas'] += gas_usage[i]

    monthly_dates = sorted(monthly_usage.keys())
    monthly_elec_usage = [monthly_usage[m]['elec'] for m in monthly_dates]
    monthly_gas_usage = [monthly_usage[m]['gas'] for m in monthly_dates]
    
    yearly_dates = sorted(yearly_usage.keys())
    yearly_elec_usage = [yearly_usage[y]['elec'] for y in yearly_dates]
    yearly_gas_usage = [yearly_usage[y]['gas'] for y in yearly_dates]

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
    recent_topups = TopUp.objects.all().order_by('-date')[:100]
    
    # Chart payload (daily arrays)
    chart_payload = {
        'dates': chart_dates,
        'elec_usage': elec_usage,
        'gas_usage': gas_usage,
        'elec_readings': elec_readings,
        'gas_readings': gas_readings,
        'elec_balance': elec_balance,
        'gas_balance': gas_balance,
        'monthly_dates': monthly_dates,
        'monthly_elec_usage': monthly_elec_usage,
        'monthly_gas_usage': monthly_gas_usage,
        'yearly_dates': yearly_dates,
        'yearly_elec_usage': yearly_elec_usage,
        'yearly_gas_usage': yearly_gas_usage,
        'topup_points': [
            {'date': t.date.date().isoformat(), 'meter': t.meter, 'amount': float(t.amount), 'note': t.note}
            for t in recent_topups
        ]
    }

    context = {
        'reading_form': reading_form,
        'topup_form': topup_form,
        'chart_payload': chart_payload,
        'last_30_rows': last_30_rows,
        'last_30_dates': [d.isoformat() for d in last_30_dates],
        'recent_topups': recent_topups,
    }
    return render(request, 'utility_home.html', context)
