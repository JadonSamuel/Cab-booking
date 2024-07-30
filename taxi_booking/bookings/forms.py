from django import forms
from .models import Booking
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User,Group
from django.core.exceptions import ValidationError
from django.utils import timezone


class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['pickup_point', 'drop_point', 'pickup_time']

    pickup_time = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            attrs={
                'type': 'datetime-local',
                'class': 'form-control'},
            format='%Y-%m-%dT%H:%M'
        )
    )

    def clean_pickup_time(self):
        pickup_time = self.cleaned_data.get('pickup_time')
        current_time = timezone.now()
        print(f"pickup_time: {pickup_time}, current_time: {current_time}")

        if pickup_time and pickup_time < current_time:
            raise ValidationError("The pickup time cannot be in the past. Please select a valid future date and time.")
        
        return pickup_time

    

class ModifyBookingForm(forms.Form):
    booking_id = forms.IntegerField()
    pickup_point = forms.ChoiceField(choices=[(p, p) for p in ['A', 'B', 'C', 'D', 'E', 'F']])
    drop_point = forms.ChoiceField(choices=[(p, p) for p in ['A', 'B', 'C', 'D', 'E', 'F']])
    pickup_time = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            attrs={
                'type': 'datetime-local',
                'class': 'form-control'},
            format='%Y-%m-%dT%H:%M'
        )
    )
    
    def clean_pickup_time(self):
        pickup_time = self.cleaned_data.get('pickup_time')
        current_time = timezone.now()
        print(f"pickup_time: {pickup_time}, current_time: {current_time}")

        if pickup_time and pickup_time < current_time:
            raise ValidationError("The pickup time cannot be in the past. Please select a valid future date and time.")
        
        return pickup_time

    

class CancelBookingForm(forms.Form):
    booking_id = forms.IntegerField(label="Booking ID")
    customer_name = forms.CharField(max_length=255, label="Customer Name")



class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField()
    group = forms.ModelChoiceField(queryset=Group.objects.all(), required=True, label="Role")

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2','group']