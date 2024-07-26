from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

def admin_required(function):
    def wrap(request, *args, **kwargs):
        if request.user.is_superuser:
            return function(request, *args, **kwargs)
        else:
            messages.error(request, "You do not have permission to view this page.")
            return redirect(reverse('index'))
    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap

def driver_required(function):
    def wrap(request, *args, **kwargs):
        if request.user.groups.filter(name='Driver').exists():
            return function(request, *args, **kwargs)
        else:
            messages.error(request, "You do not have permission to view this page.")
            return redirect(reverse('index'))  
    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap

def customer_required(function):
    def wrap(request, *args, **kwargs):
        if hasattr(request.user, 'customer'):
            return function(request, *args, **kwargs)
        else:
            messages.error(request, "You do not have permission to view this page.")
            return redirect(reverse('index')) 
    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap
