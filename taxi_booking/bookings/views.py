from django.shortcuts import render, redirect, get_object_or_404,HttpResponse
from django.contrib import messages
from .models import Customer, Taxi, Booking
from .forms import BookingForm,CancelBookingForm,ModifyBookingForm,TimeInputForm,UserRegistrationForm
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.decorators import login_required,user_passes_test
from .decorators import driver_group_required
from django.contrib.auth.models import User, Group


def create_groups_view(request):
    groups = ['Admin', 'Driver', 'Customer']
    
    for group_name in groups:
        group, created = Group.objects.get_or_create(name=group_name)
        if created:
            print(f'Successfully created group "{group_name}"')
        else:
            print(f'Group "{group_name}" already exists')

    return HttpResponse("Groups created successfully")


points = ['A', 'B', 'C', 'D', 'E', 'F']

def index(request):
    return render(request, 'index.html')

def calculate_amount(pickup_point, drop_point):
    pickup_index = points.index(pickup_point)
    drop_index = points.index(drop_point)
    distance = abs(drop_index - pickup_index) * 15
    if distance <= 5:
        fare = 100
    else:
        fare = 100 + (distance - 5) * 10
    return fare

def calculate_travel_time(point1, point2):
    return abs(points.index(point1) - points.index(point2))

def get_distance(point1, point2):
    if point1 in points and point2 in points:
        return abs(points.index(point1) - points.index(point2)) * 15
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
        if last_booking.drop_time + timedelta(hours=travel_time_to_pickup) > pickup_time:
            return False

    next_booking = Booking.objects.filter(
        taxi=taxi,
        pickup_time__gte=drop_time
    ).order_by('pickup_time').first()

    if next_booking:
        travel_time_to_next = calculate_travel_time(drop_point, next_booking.pickup_point)
        if drop_time + timedelta(hours=travel_time_to_next) > next_booking.pickup_time:
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
def book_taxi(request):
    if request.method == 'POST':
        form = BookingForm(request.POST)
        if form.is_valid():
            customer_name = form.cleaned_data['customer']
            pickup_point = form.cleaned_data['pickup_point']
            drop_point = form.cleaned_data['drop_point']
            pickup_time = form.cleaned_data['pickup_time']
            booking_time = timezone.now()
            booking_date = timezone.now().date()

            if pickup_point == drop_point or pickup_point not in points or drop_point not in points:
                messages.error(request, "Invalid pickup or drop point. Please try again.")
                return redirect('book_taxi')

            customer, created = Customer.objects.get_or_create(customer_name=customer_name)

            travel_time = calculate_travel_time(pickup_point, drop_point)
            drop_time = pickup_time + timedelta(hours=travel_time)

            
            reassigned, old_taxi, new_taxi = try_reassign_booking(pickup_point, drop_point, pickup_time, drop_time, customer)

            if reassigned:
                    messages.warning(request, f"Booking successful after reassignment. Taxi {old_taxi.taxi_id} was reassigned your trip. Taxi {new_taxi.taxi_id} took over its previous booking.")
                    return redirect('display_taxi_details')
            
          
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
                if booking.pickup_time > timezone.now():
                    available_taxi.current_location = 'A'
                    available_taxi.location_index = 0
                
                else:
                    available_taxi.current_location = pickup_point
                    available_taxi.location_index = points.index(pickup_point)
                    
                available_taxi.earnings += fare 
                available_taxi.save()
                messages.success(request, f"Taxi booked successfully! Booking ID: {booking.booking_id}")
                return redirect('display_taxi_details')
            else:
                messages.error(request, "No taxis available for the requested time. Please try a different time.")
        else:
            messages.error(request, "Invalid form data. Please check your inputs.")
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
        distance_to_pickup = abs(taxi.location_index - points.index(pickup_point))
        taxi_distances.append((taxi, distance_to_pickup))

    
    sorted_taxis = sorted(taxi_distances, key=lambda x: (x[1], x[0].earnings))
    
    for taxi, _ in sorted_taxis:
        if is_taxi_available(taxi, pickup_point, drop_point, pickup_time, drop_time):
            return taxi

    return None


def try_reassign_booking(pickup_point, drop_point, pickup_time, drop_time, customer):
    potential_bookings = Booking.objects.filter(pickup_time__gt=pickup_time).order_by('pickup_time')

    for booking in potential_bookings:
        for other_taxi in Taxi.objects.exclude(taxi_id=booking.taxi.taxi_id):
            if is_taxi_available(other_taxi, booking.pickup_point, booking.drop_point, booking.pickup_time, booking.drop_time):
                if is_taxi_available(booking.taxi, pickup_point, drop_point, pickup_time, drop_time):
                    old_taxi = booking.taxi
                    
                
                    existing_fare = booking.fare_amount
                    new_fare = calculate_amount(pickup_point, drop_point)

                   
                    booking.taxi = other_taxi
                    booking.save()

                    other_taxi.earnings += existing_fare
                    if booking.pickup_time > timezone.now():
            
                     other_taxi.current_location = 'A'
                     other_taxi.location_index = 0
                    other_taxi.save()

                    old_taxi.earnings -= existing_fare  
                    old_taxi.earnings += new_fare  
                    if pickup_time > timezone.now():
                        old_taxi.current_location = 'A'
                        old_taxi.location_index = 0
                    old_taxi.save()

                   
                    new_booking = Booking.objects.create(
                        taxi=old_taxi,
                        customer=customer,
                        pickup_point=pickup_point,
                        drop_point=drop_point,
                        pickup_time=pickup_time,
                        drop_time=drop_time,
                        fare_amount=new_fare,
                        booking_date=timezone.now().date(),
                        booking_time=timezone.now()
                    )

                    return True, old_taxi, other_taxi

    return False, None, None

@login_required
def display_bookings(request):
    
    if request.user.groups.filter(name='Driver').exists():
        return redirect('driver_dashboard')

    
    bookings = Booking.objects.all().order_by('-booking_date', '-booking_time')
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
        'sort_order': sort_order
    }
    return render(request, 'display_taxi_details.html', context)

@login_required
def modify_booking(request):
    booking_id = request.GET.get('booking_id')

    if booking_id:
        booking = get_object_or_404(Booking, booking_id=booking_id)
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
                    
                    
                    if booking.pickup_time > timezone.now():
            
                     original_taxi.current_location = 'A'
                     original_taxi.location_index = 0
                    original_taxi.earnings = original_taxi.earnings - original_fare + fare
                    original_taxi.save()

                    messages.success(request, f"Booking modified successfully for Taxi-{original_taxi.taxi_id}.")
                else:
                    available_taxi = find_available_taxi(new_pickup_point, new_drop_point, new_pickup_time, new_drop_time)

                    if available_taxi:
                        fare = calculate_amount(new_pickup_point, new_drop_point)

                        if booking.pickup_time > timezone.now():
            
                         original_taxi.current_location = 'A'
                         original_taxi.location_index = 0
                        original_taxi.earnings -= original_fare
                        original_taxi.save()

                        
                        booking.taxi = available_taxi
                        booking.pickup_point = new_pickup_point
                        booking.drop_point = new_drop_point
                        booking.pickup_time = new_pickup_time
                        booking.drop_time = new_drop_time
                        booking.fare_amount = fare
                        booking.save()

                        
                        if booking.pickup_time > timezone.now():
            
                         available_taxi.current_location = 'A'
                         available_taxi.location_index = 0
                        available_taxi.earnings += fare
                        available_taxi.save()

                        messages.warning(request, f"Booking modified and reassigned to Taxi-{available_taxi.taxi_id} successfully.")
                    else:
                        messages.error(request, "Cannot modify booking. No available taxis for the new schedule.")
                        return render(request, 'modify_booking.html', {'form': form, 'booking': booking})

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

@login_required
def cancel_booking(request):
    if request.method == 'POST':
        form = CancelBookingForm(request.POST)
        if form.is_valid():
            booking_id = form.cleaned_data['booking_id']
            customer_name = form.cleaned_data['customer_name']

            try:
                booking = Booking.objects.get(booking_id=booking_id)

                if booking.customer.customer_name != customer_name:
                    messages.error(request, "Customer name does not match the booking.")
                    return render(request, 'cancel_booking.html', {'form': form})

                taxi = booking.taxi
                fare_amount = booking.fare_amount

                booking.delete()

                taxi.earnings = max(0, taxi.earnings - fare_amount)
                taxi.save()

                remaining_bookings = Booking.objects.filter(taxi=taxi)
                if not remaining_bookings.exists():
                    taxi.current_location = 'A'
                    taxi.location_index = 0
                    taxi.save()

                messages.success(request, f"Booking (ID: {booking_id}) for {customer_name} has been cancelled successfully.")
                return redirect('display_taxi_details')

            except Booking.DoesNotExist:
                messages.error(request, "No booking found with the provided ID.")
                return render(request, 'cancel_booking.html', {'form': form})
    else:
        form = CancelBookingForm()
        

    return render(request, 'cancel_booking.html', {'form': form})

@login_required
def view_customer_trips(request, customer_id):
    customer_bookings = Booking.objects.filter(customer_id=customer_id)
    return render(request, 'customer_trips.html', {'customer_bookings': customer_bookings})

@login_required
def view_trips(request):
    form = TimeInputForm()
    trips = []
    current_time = None

    if request.method == 'POST':
        form = TimeInputForm(request.POST)
        if form.is_valid():
            specific_time = form.cleaned_data['specific_time']
            current_time = specific_time

            trips = Booking.objects.all().order_by('taxi__taxi_id')

            taxi_locations = {taxi.taxi_id: taxi.current_location for taxi in Taxi.objects.all()}

            for trip in trips:
                if trip.drop_time <= specific_time:
                    trip.status = 'Completed'
                    trip.taxi_location = trip.drop_point
                    
                elif trip.pickup_time <= specific_time < trip.drop_time:
                    trip.status = 'In Progress'
                    trip.taxi_location = trip.pickup_point  
                else:
                    trip.status = 'Scheduled'
                    trip.taxi_location = taxi_locations.get(trip.taxi_id, 'A')  

    return render(request, 'view_trips.html', {'form': form, 'trips': trips, 'current_time': current_time})


def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created for {username}. You can now log in.')
            return redirect('login')
    else:
        form = UserRegistrationForm()
    return render(request, 'register.html', {'form': form})


@login_required
@driver_group_required
def driver_dashboard(request):
    
    bookings = Booking.objects.all().order_by('-booking_date', '-booking_time')
    
    context = {
        'bookings': bookings,
        'user_role': 'Driver'
    }
    return render(request, 'driver_dashboard.html', context)


def is_admin(user):
    return user.is_superuser

@user_passes_test(is_admin)
def user_group_list(request):
    users = User.objects.all()
    user_groups = {user: user.groups.all() for user in users}

    context = {
        'user_groups': user_groups
    }
    return render(request, 'user_group_list.html', context)