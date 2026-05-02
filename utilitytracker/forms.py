# utilitytracker/forms.py
from django import forms
from .models import UtilityReading, TopUp

class UtilityReadingForm(forms.ModelForm):
    class Meta:
        model = UtilityReading
        fields = ['date', 'electricity', 'gas']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'ph-field', 'type': 'date'}),
            'electricity': forms.NumberInput(attrs={'class': 'ph-field', 'step': '0.01', 'placeholder': 'e.g. 35.00'}),
            'gas': forms.NumberInput(attrs={'class': 'ph-field', 'step': '0.01', 'placeholder': 'e.g. 30.50'}),
        }

class TopUpForm(forms.ModelForm):
    class Meta:
        model = TopUp
        fields = ['date', 'meter', 'amount', 'note']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'ph-field', 'type': 'date'}),
            'meter': forms.Select(attrs={'class': 'ph-field'}),
            'amount': forms.NumberInput(attrs={'class': 'ph-field', 'step': '0.01'}),
            'note': forms.TextInput(attrs={'class': 'ph-field'}),
        }
