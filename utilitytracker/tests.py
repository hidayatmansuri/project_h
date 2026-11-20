from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from . import selectors, services
from .models import TopUp, UtilityReading

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
        from projectauth.test_helpers import grant_test_client_app_access

        grant_test_client_app_access(self.client, "utilitytracker")
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

    def test_monthly_and_yearly_usage_aggregates_all_history_with_topups(self):
        """Monthly and yearly series include all historical readings and account for top-ups."""
        UtilityReading.objects.create(date=date(2024, 11, 15), electricity=Decimal('50.00'), gas=Decimal('40.00'))
        UtilityReading.objects.create(date=date(2024, 11, 25), electricity=Decimal('35.50'), gas=Decimal('30.00'))
        TopUp.objects.create(
            date=timezone.make_aware(datetime(2024, 12, 5, 12, 0)),
            meter='electricity',
            amount=Decimal('20.00'),
        )
        UtilityReading.objects.create(date=date(2024, 12, 10), electricity=Decimal('45.00'), gas=Decimal('22.25'))
        UtilityReading.objects.create(date=date(2025, 1, 15), electricity=Decimal('32.30'), gas=Decimal('15.10'))

        payload = selectors.get_utility_data_for_charts()

        # Daily series remains bounded to the last 30 days
        self.assertEqual(payload['dates'], [])
        # Monthly and yearly cover full history across months and years
        self.assertEqual(payload['monthly_dates'], ['2024-11', '2024-12', '2025-01'])
        self.assertEqual(payload['monthly_elec_usage'], [14.5, 10.5, 12.7])
        self.assertEqual(payload['monthly_gas_usage'], [10.0, 7.75, 7.15])
        self.assertEqual(payload['yearly_dates'], ['2024', '2025'])
        self.assertEqual(payload['yearly_elec_usage'], [25.0, 12.7])
        self.assertEqual(payload['yearly_gas_usage'], [17.75, 7.15])

    def test_monthly_and_yearly_usage_empty_and_single_reading(self):
        """Empty DB and a single baseline reading return empty monthly and yearly lists."""
        empty_payload = selectors.get_utility_data_for_charts()
        self.assertEqual(empty_payload['monthly_dates'], [])
        self.assertEqual(empty_payload['yearly_dates'], [])

        UtilityReading.objects.create(date=date(2024, 6, 1), electricity=Decimal('25.00'), gas=Decimal('15.00'))
        single_payload = selectors.get_utility_data_for_charts()
        self.assertEqual(single_payload['monthly_dates'], [])
        self.assertEqual(single_payload['yearly_dates'], [])

    def test_utility_view_payload_includes_monthly_and_yearly(self):
        """Utility view renders filter radios and passes monthly/yearly payload arrays."""
        from projectauth.test_helpers import grant_test_client_app_access

        grant_test_client_app_access(self.client, "utilitytracker")
        UtilityReading.objects.create(date=date(2024, 11, 1), electricity=Decimal('40.00'), gas=Decimal('30.00'))
        UtilityReading.objects.create(date=date(2024, 12, 1), electricity=Decimal('28.00'), gas=Decimal('21.00'))

        response = self.client.get('/utility')
        self.assertEqual(response.status_code, 200)
        chart_payload = response.context['chart_payload']
        for key in (
            'monthly_dates',
            'monthly_elec_usage',
            'monthly_gas_usage',
            'yearly_dates',
            'yearly_elec_usage',
            'yearly_gas_usage',
        ):
            self.assertIn(key, chart_payload)
        self.assertEqual(chart_payload['monthly_dates'], ['2024-12'])
        self.assertEqual(chart_payload['yearly_dates'], ['2024'])
        self.assertContains(response, 'value="monthly"')
        self.assertContains(response, 'value="yearly"')