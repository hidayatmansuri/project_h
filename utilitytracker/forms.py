from django import forms
from .models import UtilityReading, TopUp, MeterConfig

class UtilityReadingForm(forms.ModelForm):
    class Meta:
        model = UtilityReading
        fields = ['electricity', 'gas']
        widgets = {
            'electricity': forms.NumberInput(attrs={'class': 'ph-field', 'placeholder': 'Electricity'}),
            'gas': forms.NumberInput(attrs={'class': 'ph-field', 'placeholder': 'Gas'}),
        }

class TopUpForm(forms.ModelForm):
    class Meta:
        model = TopUp
        fields = ['meter', 'credit', 'note']
        widgets = {
            'meter': forms.Select(attrs={'class': 'ph-field'}),
            'credit': forms.NumberInput(attrs={'class': 'ph-field', 'placeholder': 'Credit', 'step': '0.01'}),
            'note': forms.TextInput(attrs={'class': 'ph-field', 'placeholder': 'Note'}),
        }

# class MeterConfigForm(forms.ModelForm):
#     class Meta:
#         model = MeterConfig
#         fields = ['meter', 'starting_balance', 'tariff']