"""Stats used by the admin-facing employee/manager management screens."""

from app.models import Inquiry, STATUS_CANCELLED, STATUS_CLOSED
from app.services.inquiries import get_active_inquiry


def employee_stats(employee_id):
    all_inquiries = Inquiry.query.filter_by(employee_id=employee_id).all()
    return {
        "active": get_active_inquiry(employee_id),
        "total": len(all_inquiries),
        "closed": sum(1 for i in all_inquiries if i.status == STATUS_CLOSED),
        "cancelled": sum(1 for i in all_inquiries if i.status == STATUS_CANCELLED),
        "history": sorted(all_inquiries, key=lambda i: i.created_at, reverse=True),
    }
