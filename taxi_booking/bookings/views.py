import threading
from threading import Timer
from threading import Lock
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Customer, Taxi, Booking
from .forms import BookingForm,CancelBookingForm,ModifyBookingForm,UserRegistrationForm,CustomerRegistrationForm
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from .decorators import driver_required,admin_required,customer_required
from django.contrib.auth.models import User,Group
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth import login
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils.html import strip_tags
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST
import stripe
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt


stripe.api_key = settings.STRIPE_TEST_SECRET_KEY

def create_payment_intent(amount):
    intent = stripe.PaymentIntent.create(
        amount=amount,
        currency='usd',
    )
    return intent.client_secret



@csrf_exempt
def payment_view(request):
    if request.method == 'POST':
        payment_method_id = request.POST.get('payment_method_id')
        payment_intent_id = request.POST.get('payment_intent_id')
        
        try:
            
            if not payment_intent_id:
                amount = 35000 
                intent = stripe.PaymentIntent.create(
                    amount=amount,
                    currency='usd',
                    payment_method_types=['card'],
                    automatic_payment_methods={
                        'enabled': True,
                        'allow_redirects': 'never'
                    }
                )
                payment_intent_id = intent.id

            
            confirmed_intent = stripe.PaymentIntent.confirm(
                payment_intent_id,
                payment_method=payment_method_id,
            )

            
            if confirmed_intent.status == 'succeeded':
            
                booking_details = request.session.get('booking_details')
                if booking_details:
                    Booking.objects.create(
                        taxi_id=booking_details['taxi_id'],
                        customer_id=booking_details['customer_id'],
                        pickup_point=booking_details['pickup_point'],
                        drop_point=booking_details['drop_point'],
                        pickup_time=booking_details['pickup_time'],
                        drop_time=booking_details['drop_time'],
                        fare_amount=booking_details['fare_amount'],
                        booking_date=booking_details['booking_date'],
                        booking_time=booking_details['booking_time'],
                    )
                return redirect('payment_success')
            else:
                
                return redirect('payment_error')

        except stripe.error.StripeError as e:
            
            print(f"Stripe error: {e}")
            return redirect('payment_error')
        except Exception as e:
            
            print(f"Unexpected error: {e}")
            return redirect('payment_error')
    
    
    return redirect('payment_error')

def payment_success(request):
    messages.success(request, "Payment successful and booking confirmed!")
    return redirect('display_taxi_details')

def payment_error(request):
    messages.error(request, "Payment failed. Please try again or contact support.")
    return redirect('book_taxi')

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
    distance_units = calculate_distance(point1, point2)
    travel_time_minutes = distance_units * 15
    return travel_time_minutes

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
        if new_drop_time + timedelta(minutes=travel_time_to_next) > next_booking.pickup_time:
            return False

    return True

taxi_locks = {}

def update_taxi_location(booking_id):
    try:
        booking = Booking.objects.get(pk=booking_id)
        taxi = booking.taxi
        
        
        if taxi.taxi_id not in taxi_locks:
            taxi_locks[taxi.taxi_id] = Lock()
        
        wait_time = (booking.drop_time - timezone.now()).total_seconds()
        if wait_time > 0:
            threading.Timer(wait_time, lambda: perform_location_update(taxi.taxi_id, booking.drop_point)).start()
    except Booking.DoesNotExist:
        print(f"Booking with id {booking_id} not found.")
    except Exception as e:
        print(f"An error occurred while updating taxi location: {str(e)}")


def perform_location_update(taxi_id, new_location):
    try:
        lock = taxi_locks.get(taxi_id)
        if lock:
            with lock:  
                taxi = Taxi.objects.get(pk=taxi_id)
                taxi.current_location = new_location
                taxi.location_index = points.index(new_location)
                taxi.save()
                print(f"Taxi {taxi.taxi_id} location updated to {new_location}")
        else:
            print(f"No lock found for taxi {taxi_id}")
    except Taxi.DoesNotExist:
        print(f"Taxi with id {taxi_id} not found.")
    except Exception as e:
        print(f"An error occurred while performing location update: {str(e)}")

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
                
                
                intent = stripe.PaymentIntent.create(
                    amount=fare * 100,  
                    currency='usd',
                    description=f'Taxi booking from {pickup_point} to {drop_point}',
                )
                client_secret = intent.client_secret

                request.session['booking_details'] = {
                    'taxi_id': available_taxi.taxi_id,
                    'customer_id': customer.customer_id,
                    'pickup_point': pickup_point,
                    'drop_point': drop_point,
                    'pickup_time': pickup_time.isoformat(),
                    'drop_time': drop_time.isoformat(),
                    'fare_amount': fare,
                    'booking_date': booking_date.isoformat(),
                    'booking_time': booking_time.isoformat(),
                    'payment_intent_id': intent.id
                }
                
                return render(request, 'payment.html', {
                    'client_secret': client_secret,
                    'stripe_public_key': settings.STRIPE_TEST_PUBLIC_KEY,
                    'payment_intent_id': intent.id
                })
            else:
                messages.error(request, "No taxis available for the requested time. Please try a different time.")
        else:
            messages.error(request, "Form is invalid")
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

            travel_time = calculate_travel_time(new_pickup_point, new_drop_point)
            new_drop_time = new_pickup_time + timedelta(minutes=travel_time)

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

                    for timer in threading.enumerate():
                            if isinstance(timer, Timer) and timer.function.__name__ == 'perform_location_update' and timer.args[0] == original_taxi.taxi_id:
                                timer.cancel()

                    update_taxi_location(booking.booking_id)

                    original_taxi.earnings = original_taxi.earnings - original_fare + fare
                    original_taxi.save()

                    messages.success(request, f"Booking modified successfully for Taxi-{original_taxi.taxi_id}.")
                else:
                    available_taxi = find_available_taxi(new_pickup_point, new_drop_point, new_pickup_time, new_drop_time)

                    if available_taxi:
                        fare = calculate_amount(new_pickup_point, new_drop_point)

                        
                        for timer in threading.enumerate():
                            if isinstance(timer, Timer) and timer.function.__name__ == 'perform_location_update' and timer.args[0] == original_taxi.taxi_id:
                                timer.cancel()
                        
                        original_taxi.earnings -= original_fare
                        original_taxi.save()

                        
                        booking.taxi = available_taxi
                        booking.pickup_point = new_pickup_point
                        booking.drop_point = new_drop_point
                        booking.pickup_time = new_pickup_time
                        booking.drop_time = new_drop_time
                        booking.fare_amount = fare
                        booking.save()

                        
                        update_taxi_location(booking.booking_id)
                        
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
                if booking.pickup_time <= current_time:
                    messages.error(request, "Cancellation not allowed: Your pickup time has already passed.")
                    return redirect('display_taxi_details')

                taxi = booking.taxi
                fare_amount = booking.fare_amount

                
                for timer in threading.enumerate():
                    if isinstance(timer, Timer) and timer.function.__name__ == 'perform_location_update' and timer.args[0] == taxi.taxi_id:
                        timer.cancel()

                booking.delete()

                
                taxi.earnings = max(0, taxi.earnings - fare_amount)

                
                remaining_bookings = Booking.objects.filter(taxi=taxi, pickup_time__gt=current_time).order_by('pickup_time')
                for remaining_booking in remaining_bookings:
                    update_taxi_location(remaining_booking.booking_id)

                
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
        now = timezone.now() 
        context = {
            'customer_bookings': customer_bookings,
            'now': now
        }
        return render(request, 'customer_trips.html', context)
    else:
        messages.error(request, "You don't have permission to view these trips.")
        return redirect('display_taxi_details')
    

def password_reset_request(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            messages.error(request, "No user found with that email address.")
            return redirect('password_reset_request')

        
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
       
        reset_link = request.build_absolute_uri(
            f'/reset-password-confirm/{uid}/{token}/'
        )

        html_message = render_to_string('password_reset_email.html', {'reset_link': reset_link})
        plain_message = strip_tags(html_message)


        
        send_mail(
            'Password Reset Request',
            plain_message,
            'noreply@yourdomain.com',
            [email],
            html_message=html_message,
            fail_silently=False,
        )

        messages.success(request, "Password reset email has been sent.")
        return redirect('login')

    return render(request, 'password_reset_request.html')


def password_reset_confirm(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')

            if new_password != confirm_password:
                messages.error(request, "Passwords do not match.")
                return render(request, 'password_reset_confirm.html')

            if len(new_password) < 8:
                messages.error(request, "Password must be at least 8 characters long.")
                return render(request, 'password_reset_confirm.html')

           

            user.set_password(new_password)
            user.save()
            messages.success(request, "Your password has been reset successfully.")
            return redirect('login')

        return render(request, 'password_reset_confirm.html')
    else:
        messages.error(request, "The reset link is invalid or has expired.")
        return redirect('password_reset_request')
    

def send_verification_email(user, request):
    current_site = get_current_site(request)
    protocol = 'https' if request.is_secure() else 'http'
    subject = 'Activate Your Account'
    message = render_to_string('account_activation_email.html', {
        'user': user,
        'domain': current_site.domain,
        'protocol': protocol,
        'uid': urlsafe_base64_encode(force_bytes(user.pk)),
        'token': default_token_generator.make_token(user),
    })
    email = EmailMessage(subject, message, to=[user.email])
    email.content_subtype = 'html'
    email.send()


def activate(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()

        customer, created = Customer.objects.get_or_create(user=user, defaults={'customer_name': user.username})

        login(request, user)
        messages.success(request, 'Your account has been activated successfully.')
        return redirect('login')
    else:
        messages.error(request, 'The activation link is invalid or has expired.')
        return redirect('register')


def register(request):
    if request.method == 'POST':
        form = CustomerRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.email = form.cleaned_data['email']
            user.save()

            Customer.objects.create(user=user, customer_name=form.cleaned_data['username'])

            customer_group = Group.objects.get(name='Customer')
            user.groups.add(customer_group)

            send_verification_email(user, request)

            messages.success(request, 'Please check your email to activate your account.')
            return redirect('login')
    else:
        form = CustomerRegistrationForm()
    return render(request, 'register.html', {'form': form})


User = get_user_model()

@admin_required
def register_driver(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')

            
            driver_group = Group.objects.get(name='Driver')
            driver_group.user_set.add(user)

            
            available_taxi = Taxi.objects.filter(driver__isnull=True).first()
            if available_taxi:
                available_taxi.driver = user
                available_taxi.save()
                messages.success(request, f'Account created for {username}. Assigned to Taxi {available_taxi.taxi_id}. You can now log in.')
            else:
                messages.warning(request, f'Account created for {username}, but no taxis are available for assignment. You can now log in.')

            return redirect('login')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'register_driver.html', {'form': form})


          


@login_required
@driver_required
def driver_dashboard(request):
    try:
        driver_taxi = request.user.assigned_taxi
    except ObjectDoesNotExist:
        driver_taxi = None

    if not driver_taxi:
        messages.error(request, "The page is not accessible because you are not assigned to any taxi.")
        return redirect('index')  

    bookings = Booking.objects.filter(taxi=driver_taxi).order_by('-booking_date', '-booking_time')
    total_spent = sum(booking.fare_amount for booking in bookings)

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

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
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


    
