"""Computes how many inquiries are currently waiting on each admin, and the
auto status (GREEN/YELLOW/RED) that follows from it, for the admin-selection
screen.

"Waiting" means the admin still owes the employee a reply: the inquiry is
not deleted, not closed, and not yet answered (status WAITING or READ --
READ just means the admin opened it, it does not mean they replied).
"""

from app.config_values import compute_admin_status
from app.models import Inquiry, ROLE_ADMIN, STATUS_READ, STATUS_WAITING, User

WAITING_STATUSES = (STATUS_WAITING, STATUS_READ)


def waiting_count_for_admin(admin_id):
    return Inquiry.query.filter(
        Inquiry.admin_id == admin_id,
        Inquiry.is_deleted.is_(False),
        Inquiry.status.in_(WAITING_STATUSES),
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
