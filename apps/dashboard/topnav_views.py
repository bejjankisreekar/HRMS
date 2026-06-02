"""Top navigation API views."""

from __future__ import annotations

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect

from .notification_service import (
    get_user_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    serialize_notification,
    unread_notification_count,
)
from .topnav import global_search


class GlobalSearchAPIView(LoginRequiredMixin, View):
    def get(self, request):
        q = request.GET.get("q", "")
        results = global_search(request.user, q)
        return JsonResponse({"ok": True, "results": results})


@method_decorator(csrf_protect, name="dispatch")
class NotificationListAPIView(LoginRequiredMixin, View):
    def get(self, request):
        notifications = get_user_notifications(request.user, sync=True)
        unread = unread_notification_count(request.user, sync=False)
        return JsonResponse(
            {
                "ok": True,
                "notifications": [serialize_notification(n) for n in notifications],
                "unread_count": unread,
            }
        )


@method_decorator(csrf_protect, name="dispatch")
class NotificationReadAPIView(LoginRequiredMixin, View):
    def patch(self, request, pk):
        notif = mark_notification_read(request.user, pk)
        if not notif:
            return JsonResponse({"ok": False, "error": "Notification not found"}, status=404)
        unread = unread_notification_count(request.user, sync=False)
        return JsonResponse(
            {
                "ok": True,
                "notification": serialize_notification(notif),
                "unread_count": unread,
            }
        )

    def post(self, request, pk):
        return self.patch(request, pk)


@method_decorator(csrf_protect, name="dispatch")
class NotificationReadAllAPIView(LoginRequiredMixin, View):
    def patch(self, request):
        count = mark_all_notifications_read(request.user)
        notifications = get_user_notifications(request.user, sync=False)
        return JsonResponse(
            {
                "ok": True,
                "marked_count": count,
                "unread_count": 0,
                "notifications": [serialize_notification(n) for n in notifications],
            }
        )

    def post(self, request):
        return self.patch(request)
