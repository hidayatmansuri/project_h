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
