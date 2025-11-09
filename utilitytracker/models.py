from django.db import models
from django.utils import timezone

# Create your models here.
METER_CHOICES = (
    ('electricity', 'Electricity'),
    ('gas', 'Gas'),
)

class UtilityReading(models.Model):
    date = models.DateTimeField(default=timezone.now, unique=True)
    electricity = models.FloatField(null=True, blank=True)
    gas = models.FloatField(null=True, blank=True)

    
    def __str__(self):
        return f"{self.date} - E:{self.electricity} | G:{self.gas}"


class TopUp(models.Model):
    date = models.DateTimeField(default=timezone.now)
    meter = models.CharField(max_length=11, choices=METER_CHOICES)
    credit = models.DecimalField(max_digits=10, decimal_places=2, help_text="Top up amount £")
    note = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.date.date()} {self.meter} + {self.credit}"

class MeterConfig(models.Model):
    meter = models.CharField(max_length=20, choices=METER_CHOICES, unique=True)
    starting_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tariff = models.DecimalField(max_digits=8, decimal_places=4, help_text="Currency per unit (e.g. £ per kWh)", default=0.20)

    def __str__(self):
        return f"{self.meter} config"
