"""Computes how many conversations are currently waiting on each admin, and
the auto status (GREEN/YELLOW/RED) that follows from it, for the admin
selection screen and sidebar.

Per spec section 12, an admin's waiting count is:
    admin_id = X AND is_deleted = false AND status != CLOSED
    AND waiting_for = ADMIN

`waiting_for` only flips to EMPLOYEE when the admin actually replies --
merely opening/reading a conversation does not clear it, so a read-but-
not-yet-answered conversation still counts toward workload.
"""

from app.config_values import compute_admin_status
from app.models import Inquiry, ROLE_ADMIN, STATUS_CLOSED, User, WAITING_FOR_ADMIN


def waiting_count_for_admin(admin_id):
    return Inquiry.query.filter(
        Inquiry.admin_id == admin_id,
        Inquiry.is_deleted.is_(False),
        Inquiry.status != STATUS_CLOSED,
        Inquiry.waiting_for == WAITING_FOR_ADMIN,
    ).count()


def admins_with_status():
    """List of {user, waiting_count, status} for every admin, in a stable
    order, for the employee-facing admin-selection screen."""
    admins = User.query.filter_by(role=ROLE_ADMIN).order_by(User.name).all()
    result = []
    for admin in admins:
        count = waiting_count_for_admin(admin.id)
        result.append(
            {
                "user": admin,
                "waiting_count": count,
                "status": compute_admin_status(count),
            }
        )
    return result
