from django.db import models
from django.db import models
from django.contrib.auth.models import User


class Customer(models.Model):
    user = models.OneToOneField(User, null=True, blank=True, on_delete=models.SET_NULL)
    customer_id = models.AutoField(primary_key=True)
    customer_name = models.CharField(max_length=255)

    

class Taxi(models.Model):
    taxi_id = models.AutoField(primary_key=True)
    driver = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, related_name='assigned_taxi')
    current_location = models.CharField(max_length=1, choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D'), ('E', 'E'), ('F', 'F')],default='A')
    earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    location_index = models.IntegerField(default=0)

    def __str__(self):
        return f"Taxi {self.taxi_id}"


   

   
class Booking(models.Model):
    booking_id = models.AutoField(primary_key=True)
    taxi = models.ForeignKey(Taxi, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    pickup_point = models.CharField(max_length=1, choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D'), ('E', 'E'), ('F', 'F')])
    drop_point = models.CharField(max_length=1, choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D'), ('E', 'E'), ('F', 'F')])
    pickup_time = models.DateTimeField()
    drop_time = models.DateTimeField(default=None, null=True, blank=True)
    booking_time = models.TimeField(auto_now_add=True)
    booking_date = models.DateField(auto_now_add=True)
    fare_amount = models.DecimalField(max_digits=10, decimal_places=2,default=0)

 
