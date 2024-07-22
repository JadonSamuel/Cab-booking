from django import forms
from .models import Booking
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User,Group,Permission


class BookingForm(forms.ModelForm):
    customer = forms.CharField(max_length=255)
    
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


class CancelBookingForm(forms.Form):
    booking_id = forms.IntegerField(label="Booking ID")
    customer_name = forms.CharField(max_length=255, label="Customer Name")


class TimeInputForm(forms.Form):
    specific_time = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            attrs={
                'type': 'datetime-local',
                'class': 'form-control'},
            format='%Y-%m-%dT%H:%M'
        )
    )

class UserRegistrationForm(UserCreationForm):
    groups = forms.ModelMultipleChoiceField(queryset=Group.objects.all(), required=False)
    user_permissions = forms.ModelMultipleChoiceField(queryset=Permission.objects.all(), required=False)
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')