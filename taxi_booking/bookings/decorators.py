from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect


def driver_group_required(view_func):
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.groups.filter(name='Driver').exists():
            messages.error(request, "Only Drivers can view booking.")
            return redirect('login') 
        return view_func(request, *args, **kwargs)
    return _wrapped_view
