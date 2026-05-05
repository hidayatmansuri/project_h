# utilitytracker/selectors.py
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal, InvalidOperation
from collections import defaultdict
from .models import UtilityReading, TopUp

def get_utility_data_for_charts():
    """
    Logic for calculating usage and preparing chart payloads.
    """
    readings_qs = UtilityReading.objects.all().order_by('date')
    readings = list(readings_qs)
    topups_qs = TopUp.objects.all().order_by('date')
    topups = list(topups_qs)

    topups_by_date = {}
    for t in topups:
        d = t.date.date()
        topups_by_date.setdefault(d, []).append(t)

    # Last 30 days only on Graph
    today = timezone.now().date()
    cutoff = today - timedelta(days=30)
    readings_30 = [r for r in readings if r.date >= cutoff]
    
    chart_dates = []
    elec_usage = []
    gas_usage = []
    elec_readings = []
    gas_readings = []
    
    for r in readings_30:
        chart_dates.append(r.date.isoformat())
        elec_readings.append(float(r.electricity) if r.electricity is not None else None)
        gas_readings.append(float(r.gas) if r.gas is not None else None)

    prev = None
    for r in readings_30:
        if prev is None:
            elec_usage.append(0.0)
            gas_usage.append(0.0)
            prev = r
            continue

        elec_topups_sum = Decimal('0.00')
        gas_topups_sum = Decimal('0.00')
        for t in topups:
            t_date = t.date.date()
            if prev.date < t_date <= r.date:
                if t.meter == 'electricity':
                    elec_topups_sum += Decimal(t.amount)
                elif t.meter == 'gas':
                    gas_topups_sum += Decimal(t.amount)

        eu = 0.0
        gu = 0.0

        if prev.electricity is not None and r.electricity is not None:
            try:
                eu_calc = (Decimal(prev.electricity) - (Decimal(r.electricity) - elec_topups_sum))
                eu = float(eu_calc) if eu_calc > 0 else 0.0
            except (InvalidOperation, TypeError):
                eu = 0.0

        if prev.gas is not None and r.gas is not None:
            try:
                gu_calc = (Decimal(prev.gas) - (Decimal(r.gas) - gas_topups_sum))
                gu = float(gu_calc) if gu_calc > 0 else 0.0
            except (InvalidOperation, TypeError):
                gu = 0.0

        elec_usage.append(round(eu, 2))
        gas_usage.append(round(gu, 2))
        prev = r
    
    elec_balance = []
    gas_balance = []
    balance_e = 0.0
    balance_g = 0.0

    for i, d_str in enumerate(chart_dates):
        d = date.fromisoformat(d_str)

        for t in topups_by_date.get(d, []):
            if t.meter == 'electricity':
                balance_e += float(t.amount)
            elif t.meter == 'gas':
                balance_g += float(t.amount)

        balance_e -= elec_usage[i]
        balance_g -= gas_usage[i]

        elec_balance.append(round(balance_e, 2))
        gas_balance.append(round(balance_g, 2))

    monthly_usage = defaultdict(lambda: {'elec':0.0, 'gas':0.0})
    yearly_usage = defaultdict(lambda: {'elec':0.0, 'gas':0.0})
    for i, d in enumerate(chart_dates):
        month_key = d[:7]
        year_key = d[:4]
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

    recent_topups = get_recent_topups()
    
    return {
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

def get_last_30_days_readings():
    """
    Logic for preparing the readings table for the last 30 days.
    """
    today = timezone.now().date()
    last_30_dates = [today - timedelta(days=i) for i in reversed(range(30))]
    readings = UtilityReading.objects.filter(date__in=last_30_dates)
    readings_map = {r.date: r for r in readings}

    last_30_rows = []
    for d in reversed(last_30_dates):
        r = readings_map.get(d)
        if r and (r.electricity is not None or r.gas is not None):
            last_30_rows.append({
                'date': d.isoformat(),
                'electricity': float(r.electricity) if r.electricity is not None else None,
                'gas': float(r.gas) if r.gas is not None else None,
            })
    return last_30_rows, last_30_dates

def get_recent_topups(limit=100):
    """
    Retrieves recent top-ups.
    """
    return TopUp.objects.all().order_by('-date')[:limit]