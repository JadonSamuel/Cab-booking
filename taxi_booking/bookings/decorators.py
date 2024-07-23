from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied

def admin_required(function):
    def wrap(request, *args, **kwargs):
        if request.user.is_superuser:
            return function(request, *args, **kwargs)
        else:
            raise PermissionDenied
    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap

def driver_required(function):
    def wrap(request, *args, **kwargs):
        if request.user.groups.filter(name='Driver').exists():
            return function(request, *args, **kwargs)
        else:
            raise PermissionDenied
    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap

def customer_required(function):
    def wrap(request, *args, **kwargs):
        if hasattr(request.user, 'customer'):
            return function(request, *args, **kwargs)
        else:
            raise PermissionDenied
    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap
