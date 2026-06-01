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

    def test_utility_view_update_reading(self):
        """Test that the view handles updates of existing readings via POST without uniqueness errors"""
        test_date = timezone.now().date()
        
        # 1. Create an initial reading
        UtilityReading.objects.create(date=test_date, electricity=10.00, gas=20.00)
        
        # 2. POST to the view to update that reading
        response = self.client.post('/utility', {
            'submit_reading': 'Submit',
            'date': test_date.isoformat(),
            'electricity': '15.50',
            'gas': '25.50'
        })
        
        # 3. Assert it redirects to 'utility' view
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/utility')
        
        # 4. Verify database values are updated
        reading = UtilityReading.objects.get(date=test_date)
        self.assertEqual(reading.electricity, 15.50)
        self.assertEqual(reading.gas, 25.50)