# utilitytracker/models.py
from django.db import models
from django.utils import timezone
from decimal import Decimal

METER_CHOICES = (
    ('electricity', 'Electricity'),
    ('gas', 'Gas'),
)

class UtilityReading(models.Model):
    # daily meter reading (prepay credit shown on meter) - one entry per date
    date = models.DateField(default=timezone.now, unique=True)
    electricity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    gas = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f"{self.date} — Elec: {self.electricity} | Gas: {self.gas}"


class TopUp(models.Model):
    date = models.DateTimeField(default=timezone.now)
    meter = models.CharField(max_length=20, choices=METER_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2,
                                 help_text="Currency amount added (e.g. £)")
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.date.date()} {self.meter} +{self.amount}"
