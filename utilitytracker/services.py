# utilitytracker/services.py
from .models import UtilityReading, TopUp

def create_or_update_reading(date, electricity, gas):
    """
    Handles the logic for saving or updating a meter reading.
    """
    reading, created = UtilityReading.objects.update_or_create(
        date=date,
        defaults={'electricity': electricity, 'gas': gas}
    )
    return reading

def create_topup(date, meter, amount, note=""):
    """
    Handles the logic for saving a top-up.
    """
    topup = TopUp.objects.create(
        date=date,
        meter=meter,
        amount=amount,
        note=note
    )
    return topup

def update_topup(topup_id, date, meter, amount, note=""):
    """
    Handles the logic for updating an existing top-up.
    """
    topup = TopUp.objects.get(id=topup_id)
    topup.date = date
    topup.meter = meter
    topup.amount = amount
    topup.note = note
    topup.save()
    return topup

def delete_topup(topup_id):
    """
    Handles the logic for deleting a top-up.
    """
    TopUp.objects.filter(id=topup_id).delete()

