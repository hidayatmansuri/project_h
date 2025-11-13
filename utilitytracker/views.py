from django.shortcuts import render, redirect
from django.utils import timezone
from .models import UtilityReading, TopUp, MeterConfig
from .forms import UtilityReadingForm, TopUpForm
from datetime import timedelta, date
from decimal import Decimal

def utilitytracker(request):
    # forms
    reading_form = UtilityReadingForm()
    topup_form = TopUpForm()

    if request.method == 'POST':
        # either reading submit or top-up submit; distinguish by name attribute in submit button
        if 'submit_reading' in request.POST:
            reading_form = UtilityReadingForm(request.POST)
            if reading_form.is_valid():
                r = reading_form.save(commit=False)
                r.date = timezone.now().date()
                # Optional: ensure not duplicate for same date
                UtilityReading.objects.update_or_create(date=r.date, defaults={
                    'electricity': r.electricity, 'gas': r.gas
                })
                return redirect('utilitytracker')
        elif 'submit_topup' in request.POST:
            topup_form = TopUpForm(request.POST)
            if topup_form.is_valid():
                topup_form.save()
                return redirect('utilitytracker')

    # fetch readings ordered ascending for computations
    readings_qs = UtilityReading.objects.all().order_by('date')
    readings = list(readings_qs)

    # fetch topups ordered ascending
    topups = list(TopUp.objects.all().order_by('date'))

    # load meter configs or defaults
    configs = {c.meter: c for c in MeterConfig.objects.all()}
    # ensure configs exist for both meters
    for m in ['electricity', 'gas']:
        if m not in configs:
            # fallback default (not saved)
            configs[m] = MeterConfig(meter=m, starting_balance=Decimal('0.00'), tariff=Decimal('0.20'))

    # prepare daily usage list (per day) and running balances
    # We'll compute arrays of dates, elec_usage, gas_usage, elec_balance, gas_balance
    dates = []
    elec_usage = []
    gas_usage = []
    elec_balance = []
    gas_balance = []
    # Start balances
    elec_bal = Decimal(configs['electricity'].starting_balance)
    gas_bal = Decimal(configs['gas'].starting_balance)
    # pointer for previous readings to compute usage
    prev = None

    # create maps for topups by date (datetime) for quick aggregation
    # but topups can occur with time; we'll include topups up to and including that date when computing balance for that date
    topups_by_date = {}
    for t in topups:
        d = t.date.date()
        topups_by_date.setdefault(d, []).append(t)

    # iterate through readings
    for r in readings:
        d = r.date
        # compute usage vs previous
        if prev is None:
            # no previous: cannot compute usage; treat usage as None or 0
            eu = None
            gu = None
        else:
            eu = None
            gu = None
            if prev.electricity is not None and r.electricity is not None:
                eu = r.electricity - prev.electricity
                # guard against negative or unrealistic values:
                if eu < 0:
                    eu = None
            if prev.gas is not None and r.gas is not None:
                gu = r.gas - prev.gas
                if gu < 0:
                    gu = None

        # add to lists
        dates.append(d.isoformat())
        elec_usage.append(eu if eu is not None else 0)
        gas_usage.append(gu if gu is not None else 0)

        # apply topups for this date (if any) BEFORE subtracting day's consumption
        todays_topups = topups_by_date.get(d, [])
        for t in todays_topups:
            if t.meter == 'electricity':
                elec_bal += Decimal(t.credit)
                # if units were supplied, optionally convert currency -> units or track both
                # we use currency-based balance
            elif t.meter == 'gas':
                gas_bal += Decimal(t.credit)

        # subtract consumption cost (use tariff), only if we have eu/gu
        if eu is not None:
            # tariff as Decimal
            tariff = Decimal(configs['electricity'].tariff)
            elec_bal -= Decimal(eu) * tariff
        if gu is not None:
            tariff = Decimal(configs['gas'].tariff)
            gas_bal -= Decimal(gu) * tariff

        elec_balance.append(float(elec_bal))
        gas_balance.append(float(gas_bal))

        prev = r

    # prepare chart datasets for Chart.js
    chart_payload = {
        'dates': dates,
        'elec_usage': elec_usage,
        'gas_usage': gas_usage,
        'elec_balance': elec_balance,
        'gas_balance': gas_balance,
        # topup points to mark on balance graph
        'topups': [
            {'date': t.date.date().isoformat(), 'meter': t.meter, 'credit': float(t.credit)}
            for t in topups
        ]
    }

    # last 30 days reading table (align dates row)
    today = timezone.now().date()
    start_30 = today - timedelta(days=30)
    last_30 = UtilityReading.objects.filter(date__gte=start_30).order_by('date')

    context = {
        'reading_form': reading_form,
        'topup_form': topup_form,
        'chart_payload': chart_payload,
        'last_30': last_30,
        'configs': configs,
    }
    return render(request, 'utility_home.html', context)
