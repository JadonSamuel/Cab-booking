from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Customer, Taxi, Booking
from .forms import BookingForm,CancelBookingForm,ModifyBookingForm,UserRegistrationForm
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from .decorators import driver_required,admin_required,customer_required
from django.contrib.auth.models import User

points = ['A', 'B', 'C', 'D', 'E', 'F']

def index(request):
    return render(request, 'index.html')

def calculate_distance(point1, point2):
    if point1 in points and point2 in points:
        index1 = points.index(point1)
        index2 = points.index(point2)
        distance = min(abs(index2 - index1), len(points) - abs(index2 - index1))
        return distance
    return None

def calculate_amount(pickup_point, drop_point):
    distance = calculate_distance(pickup_point, drop_point) * 15
    if distance is None:
        return None
    if distance <= 5:
        fare = 100
    else:
        fare = 100 + (distance - 5) * 10
    return fare

def calculate_travel_time(point1, point2):
    distance = calculate_distance(point1, point2) * 15
    return distance

def get_distance(point1, point2):
    distance = calculate_distance(point1, point2)
    if distance is not None:
        return distance * 15
    return None


def is_taxi_available(taxi, pickup_point, drop_point, pickup_time, drop_time):
    
    conflicting_bookings = Booking.objects.filter(
        taxi=taxi,
        pickup_time__lt=drop_time,
        drop_time__gt=pickup_time
    )
    if conflicting_bookings.exists():
        return False

    
    last_booking = Booking.objects.filter(
        taxi=taxi,
        drop_time__lte=pickup_time
    ).order_by('-drop_time').first()

    if last_booking:
        
        travel_time_to_pickup = calculate_travel_time(last_booking.drop_point, pickup_point)
        if last_booking.drop_time + timedelta(minutes=travel_time_to_pickup) > pickup_time:
            return False

    
    next_booking = Booking.objects.filter(
        taxi=taxi,
        pickup_time__gte=drop_time
    ).order_by('pickup_time').first()

    if next_booking:
        
        travel_time_to_next = calculate_travel_time(drop_point, next_booking.pickup_point)
        if drop_time + timedelta(minutes=travel_time_to_next) > next_booking.pickup_time:
            return False

    return True

def is_taxi_available_for_modification(taxi, original_booking, new_pickup_point, new_drop_point, new_pickup_time, new_drop_time):

    conflicting_bookings = Booking.objects.filter(
        taxi=taxi,
        pickup_time__lt=new_drop_time,
        drop_time__gt=new_pickup_time
    ).exclude(booking_id=original_booking.booking_id)

    if conflicting_bookings.exists():
        return False

   
    next_booking = Booking.objects.filter(
        taxi=taxi,
        pickup_time__gte=new_drop_time
    ).exclude(booking_id=original_booking.booking_id).order_by('pickup_time').first()

    if next_booking:
        travel_time_to_next = calculate_travel_time(new_drop_point, next_booking.pickup_point)
        if new_drop_time + timedelta(hours=travel_time_to_next) > next_booking.pickup_time:
            return False

    return True

@login_required
@customer_required
def book_taxi(request):
    if request.method == 'POST':
        form = BookingForm(request.POST)
        if form.is_valid():
            pickup_point = form.cleaned_data['pickup_point']
            drop_point = form.cleaned_data['drop_point']
            pickup_time = form.cleaned_data['pickup_time']

            
            
            booking_time = timezone.now()
            booking_date = timezone.now().date()

            if pickup_point == drop_point or pickup_point not in points or drop_point not in points:
                messages.error(request, "Invalid pickup or drop point. Please try again.")
                return redirect('book_taxi')

            
            customer = request.user.customer

            travel_time = calculate_travel_time(pickup_point, drop_point)
            drop_time = pickup_time + timedelta(minutes=travel_time)

            

            available_taxi = find_available_taxi(pickup_point, drop_point, pickup_time, drop_time)

            if available_taxi:
                fare = calculate_amount(pickup_point, drop_point)
                booking = Booking.objects.create(
                    taxi=available_taxi,
                    customer=customer,
                    pickup_point=pickup_point,
                    drop_point=drop_point,
                    pickup_time=pickup_time,
                    drop_time=drop_time,
                    fare_amount=fare,
                    booking_date=booking_date,
                    booking_time=booking_time
                )
                available_taxi.current_location = drop_point
                available_taxi.location_index = points.index(drop_point)

                available_taxi.earnings += fare
                available_taxi.save()
                messages.success(request, f"Taxi booked successfully! Booking ID: {booking.booking_id}")
                return redirect('display_taxi_details')
            else:
                messages.error(request, "No taxis available for the requested time. Please try a different time.")
        else:
            messages.error(request, "Form is invalid" )
    else:
        form = BookingForm()

    return render(request, 'book_taxi.html', {'form': form})


def find_available_taxi(pickup_point, drop_point, pickup_time, drop_time):
    same_point_taxis = Taxi.objects.filter(current_location=pickup_point).order_by('earnings')
    for taxi in same_point_taxis:
        if is_taxi_available(taxi, pickup_point, drop_point, pickup_time, drop_time):
            return taxi

    all_taxis = Taxi.objects.all()

    taxi_distances = []
    for taxi in all_taxis:
        distance_to_pickup = min(abs(taxi.location_index - points.index(pickup_point)), len(points) - abs(taxi.location_index - points.index(pickup_point)))
        taxi_distances.append((taxi, distance_to_pickup))

    sorted_taxis = sorted(taxi_distances, key=lambda x: (x[1], x[0].earnings))

    for taxi, _ in sorted_taxis:
        if is_taxi_available(taxi, pickup_point, drop_point, pickup_time, drop_time):
            return taxi

    return None

@login_required
def display_bookings(request):
    
    if request.user.groups.filter(name='Driver').exists():
        return redirect('driver_dashboard')

    if hasattr(request.user, 'customer'):
        bookings = Booking.objects.filter(customer=request.user.customer).order_by('-booking_date', '-booking_time')
        total_spent = sum(booking.fare_amount for booking in bookings)
    elif request.user.is_superuser:
        bookings = Booking.objects.all().order_by('-booking_date', '-booking_time')
        total_spent = 0
    else:
        messages.error(request,"You dont have access to anything")
        return redirect('index') 

    sort_order = request.POST.get('sort_order', 'asc')

    if request.method == 'POST' and 'sort_by_taxi_id' in request.POST:
        if sort_order == 'asc':
            bookings = bookings.order_by('taxi__taxi_id')
            sort_order = 'desc'
        else:
            bookings = bookings.order_by('-taxi__taxi_id')
            sort_order = 'asc'

    context = {
        'bookings': bookings,
        'sort_order': sort_order,
        'is_admin': request.user.is_superuser,
        'is_customer': hasattr(request.user, 'customer'),
        'total_spent': total_spent
    }
    return render(request, 'display_taxi_details.html', context)

@login_required
@customer_required
def modify_booking(request):
    booking_id = request.GET.get('booking_id')

    if booking_id:
        booking = get_object_or_404(Booking, booking_id=booking_id)
        
        if booking.customer.user != request.user:
            messages.error(request, "You don't have permission to modify this booking.")
            return redirect('display_taxi_details')
    else:
        messages.error(request, "No booking ID provided.")
        return redirect('display_taxi_details')

    if request.method == 'POST':
        form = ModifyBookingForm(request.POST)
        if form.is_valid():
            new_pickup_point = form.cleaned_data['pickup_point']
            new_drop_point = form.cleaned_data['drop_point']
            new_pickup_time = form.cleaned_data['pickup_time']

            if (new_pickup_point == booking.pickup_point and
                new_drop_point == booking.drop_point and
                new_pickup_time == booking.pickup_time):
                messages.info(request, "No changes were made to the booking.")
                return redirect('display_taxi_details')

            if new_pickup_point not in points or new_drop_point not in points:
                messages.error(request, "Invalid pickup or drop point. Please try again.")
                return render(request, 'modify_booking.html', {'form': form, 'booking': booking})

            travel_points = abs(points.index(new_pickup_point) - points.index(new_drop_point))
            new_drop_time = new_pickup_time + timezone.timedelta(hours=travel_points)

            try:
                original_taxi = booking.taxi
                original_fare = booking.fare_amount

                if is_taxi_available_for_modification(original_taxi, booking, new_pickup_point, new_drop_point, new_pickup_time, new_drop_time):
                    fare = calculate_amount(new_pickup_point, new_drop_point)

                    booking.pickup_point = new_pickup_point
                    booking.drop_point = new_drop_point
                    booking.pickup_time = new_pickup_time
                    booking.drop_time = new_drop_time
                    booking.fare_amount = fare
                    booking.save()

                    original_taxi.current_location = new_drop_point
                    original_taxi.location_index = points.index(new_drop_point)

                    original_taxi.earnings = original_taxi.earnings - original_fare + fare
                    original_taxi.save()

                    messages.success(request, f"Booking modified successfully for Taxi-{original_taxi.taxi_id}.")
                else:
                    available_taxi = find_available_taxi(new_pickup_point, new_drop_point, new_pickup_time, new_drop_time)

                    if available_taxi:
                        fare = calculate_amount(new_pickup_point, new_drop_point)

                        
                        subsequent_bookings = Booking.objects.filter(taxi=original_taxi, pickup_time__gt=booking.drop_time).order_by('pickup_time')
                        if subsequent_bookings.exists():
                            next_booking = subsequent_bookings.first()
                            original_taxi.current_location = next_booking.drop_point
                            original_taxi.location_index = points.index(next_booking.drop_point)
                        else:
                            original_taxi.current_location = booking.drop_point
                            original_taxi.location_index = points.index(booking.drop_point)
                        
                        original_taxi.earnings -= original_fare
                        original_taxi.save()

                        
                        booking.taxi = available_taxi
                        booking.pickup_point = new_pickup_point
                        booking.drop_point = new_drop_point
                        booking.pickup_time = new_pickup_time
                        booking.drop_time = new_drop_time
                        booking.fare_amount = fare
                        booking.save()

                        
                        subsequent_bookings = Booking.objects.filter(taxi=available_taxi, pickup_time__gt=new_drop_time).order_by('pickup_time')
                        if subsequent_bookings.exists():
                            next_booking = subsequent_bookings.first()
                            available_taxi.current_location = next_booking.pickup_point
                            available_taxi.location_index = points.index(next_booking.pickup_point)
                        else:
                            available_taxi.current_location = new_drop_point
                            available_taxi.location_index = points.index(new_drop_point)
                        
                        available_taxi.earnings += fare
                        available_taxi.save()

                        messages.warning(request, f"Booking modified and reassigned to Taxi-{available_taxi.taxi_id} successfully.")
                    else:
                        messages.error(request, "Cannot modify booking. No available taxis for the new schedule.")
                        return redirect('display_taxi_details')

                return redirect('display_taxi_details')

            except Exception as e:
                messages.error(request, f"An error occurred: {str(e)}")
                return render(request, 'modify_booking.html', {'form': form, 'booking': booking})
    else:
        form = ModifyBookingForm(initial={
            'booking_id': booking.booking_id,
            'pickup_point': booking.pickup_point,
            'drop_point': booking.drop_point,
            'pickup_time': booking.pickup_time,
        })

    return render(request, 'modify_booking.html', {'form': form, 'booking': booking})


def can_cancel_booking(booking_pickup_time, current_time):
    if booking_pickup_time <= current_time:
        return False, "Cancellation not allowed: Your pickup time has already passed."
    return True, "You can proceed with cancellation."


@login_required
@customer_required
def cancel_booking(request):
    if request.method == 'POST':
        form = CancelBookingForm(request.POST)
        if form.is_valid():
            booking_id = form.cleaned_data['booking_id']

            try:
                booking = get_object_or_404(Booking, booking_id=booking_id)

                
                if booking.customer.user != request.user:
                    messages.error(request, "You don't have permission to cancel this booking.")
                    return redirect('display_taxi_details')

                
                current_time = timezone.now()
                can_cancel, message = can_cancel_booking(booking.pickup_time, current_time)
                
                if not can_cancel:
                    messages.error(request, message)
                    return redirect('display_taxi_details')

                
                taxi = booking.taxi
                fare_amount = booking.fare_amount

                
                booking.delete()

                
                taxi.earnings = max(0, taxi.earnings - fare_amount)
                remaining_bookings = Booking.objects.filter(taxi=taxi).order_by('pickup_time')

                if remaining_bookings.exists():
                    last_booking = remaining_bookings.last()
                    taxi.current_location = last_booking.drop_point
                    taxi.location_index = points.index(last_booking.drop_point)
                else:
                    taxi.current_location = 'A'
                    taxi.location_index = 0

                taxi.save()

                messages.success(request, f"Booking (ID: {booking_id}) has been cancelled successfully.")
                return redirect('display_taxi_details')

            except Booking.DoesNotExist:
                messages.error(request, "No booking found with the provided ID.")
                return render(request, 'cancel_booking.html', {'form': form})
    else:
        form = CancelBookingForm()

    return render(request, 'cancel_booking.html', {'form': form})



@login_required
def view_customer_trips(request, customer_id):
    
    if request.user.is_superuser or (hasattr(request.user, 'customer') and request.user.customer.customer_id == customer_id):
        customer_bookings = Booking.objects.filter(customer_id=customer_id)
        return render(request, 'customer_trips.html', {'customer_bookings': customer_bookings})
    else:
        messages.error(request, "You don't have permission to view these trips.")
        return redirect('display_taxi_details')


def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            group = form.cleaned_data.get('group')
            
            group.user_set.add(user)
            
            if group.name == 'Customer':
                Customer.objects.create(user=user, customer_name=username)
                messages.success(request, f'Account created for {username}. You can now log in.')
            elif group.name == 'Driver':
                
                available_taxi = Taxi.objects.filter(driver__isnull=True).first()
                if available_taxi:
                    available_taxi.driver = user
                    available_taxi.save()
                    messages.success(request, f'Account created for {username}. Assigned to Taxi {available_taxi.taxi_id}. You can now log in.')
                else:
                    messages.warning(request, f'Account created for {username}, but no taxis are available for assignment. You can now log in.')
            else:
                messages.success(request, f'Account created for {username}. You can now log in.')
            
            return redirect('login')
    else:
        form = UserRegistrationForm()
    return render(request, 'register.html', {'form': form})


@login_required
@driver_required
def driver_dashboard(request):
    
    driver_taxi = request.user.assigned_taxi

    if driver_taxi:
        
        bookings = Booking.objects.filter(taxi=driver_taxi).order_by('-booking_date', '-booking_time')
        total_spent = sum(booking.fare_amount for booking in bookings)
    else:
    
        bookings = Booking.objects.none()
        total_spent = 0
    
    context = {
        'bookings': bookings,
        'taxi': driver_taxi,
        'user_role': 'Driver',
        'total_spent': total_spent
        
    }
    return render(request, 'driver_dashboard.html', context)


def is_admin(user):
    return user.is_superuser

@admin_required
def user_group_list(request):
    if not request.user.is_superuser:
        messages.error(request, 'You do not have permission to view this page.')
        return redirect('login')

    users = User.objects.all()
    user_groups = {user: user.groups.all() for user in users}

    context = {
        'user_groups': user_groups
    }
    return render(request, 'user_group_list.html', context)

@admin_required
def display_taxis(request):

    if not request.user.is_superuser:
        messages.error(request,'You do not have permission to view this page.')
        return redirect('login')
    
    taxis = Taxi.objects.all().order_by('taxi_id')

    context = {
        'taxis': taxis,
        'user_role': 'Admin'
    }

    return render(request, 'total_taxis.html',context)


    
