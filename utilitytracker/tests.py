from django.test import TestCase
from django.utils import timezone
from . import services
from .models import UtilityReading

class UtilityReadingTest(TestCase):

    
    def test_create_reading_services(self):
        """Test that the service correctly creates a reading"""
        # Arrange
        test_date = timezone.now().date()
        test_elec = 10.00
        test_gas = 20.00

        # Act
        services.create_or_update_reading(date=test_date, electricity=test_elec, gas=test_gas)
        
        # Assert
        # Check if 1 reading now exists in the database

        self.assertEqual(UtilityReading.objects.count(), 1)

        #Get that reading and check if values are correct

        reading = UtilityReading.objects.get(date=test_date)
        self.assertEqual(reading.electricity, 10.00)
        self.assertEqual(reading.gas, 20.00)

    def test_existing_reading(self):
        """Test that calling the services with an existing date updates the record"""
        test_date = timezone.now().date()
        
        #Create initial reading
        services.create_or_update_reading(test_date, 10.00, 20.00)
        
        #Update it with new values
        
        services.create_or_update_reading(test_date, 20.00, 30.00)

        #Assert: Still only 1 record, but with new values
        self.assertEqual(UtilityReading.objects.count(), 1)
        reading = UtilityReading.objects.get(date=test_date)
        self.assertEqual(reading.electricity, 20.00)

        