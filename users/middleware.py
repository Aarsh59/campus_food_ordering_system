from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone


class InactivityTimeoutMiddleware:
    SESSION_KEY = '_last_activity_ts'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self._handle_inactivity(request)
        if response is not None:
            return response
        return self.get_response(request)

    def _handle_inactivity(self, request):
        if not request.user.is_authenticated:
            request.session.pop(self.SESSION_KEY, None)
            return None

        timeout_seconds = getattr(
            settings,
            'SESSION_INACTIVITY_TIMEOUT',
            getattr(settings, 'SESSION_COOKIE_AGE', 3600),
        )
        now_ts = int(timezone.now().timestamp())
        last_activity_ts = request.session.get(self.SESSION_KEY)

        if last_activity_ts is not None and now_ts - int(last_activity_ts) > timeout_seconds:
            logout(request)
            messages.info(request, 'You were logged out due to inactivity. Please log in again.')
            if self._expects_json(request):
                return JsonResponse(
                    {
                        'error': 'Session expired due to inactivity',
                        'redirect_url': '/login/',
                    },
                    status=401,
                )
            return redirect('login')

        request.session[self.SESSION_KEY] = now_ts
        return None

    def _expects_json(self, request):
        accepts = request.headers.get('Accept', '')
        requested_with = request.headers.get('X-Requested-With', '')
        return 'application/json' in accepts or requested_with == 'XMLHttpRequest'
