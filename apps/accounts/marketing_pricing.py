"""Marketing pricing page — loads plans and features from database."""

from __future__ import annotations

from apps.subscriptions.services.pricing_matrix import get_pricing_page_context

__all__ = ["get_pricing_page_context"]
