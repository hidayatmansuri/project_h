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

def delete_topup(topup_id):
    """
    Handles the logic for deleting a top-up.
    """
    TopUp.objects.filter(id=topup_id).delete()

