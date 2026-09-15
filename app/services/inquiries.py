"""Core business rules for the one-active-inquiry-per-employee policy and
the delete-request / cancellation workflow.

Every check here runs regardless of what the UI shows -- these functions
are the actual gate, called from the routes, so a direct POST/DELETE that
skips the HTML forms is still blocked (spec section 1-17).
"""

from datetime import datetime

from app.extensions import db
from app.models import (
    Inquiry,
    Message,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_CLOSED,
    STATUS_WAITING,
    WAITING_FOR_ADMIN,
    WAITING_FOR_EMPLOYEE,
    WAITING_FOR_NONE,
)
from app.services.attachments import save_attachments

INACTIVE_STATUSES = (STATUS_CLOSED, STATUS_CANCELLED)


class InquiryError(Exception):
    """Raised when a requested action is not allowed by the business rules."""


def get_active_inquiry(employee_id):
    return Inquiry.query.filter(
        Inquiry.employee_id == employee_id,
        Inquiry.is_deleted.is_(False),
        Inquiry.status.notin_(INACTIVE_STATUSES),
    ).first()


def create_inquiry(employee, admin, title, content, files=None):
    if get_active_inquiry(employee.id):
        raise InquiryError("이미 처리 중인 문의가 있어 다른 관리자에게 새로운 문의를 보낼 수 없습니다.")

    inquiry = Inquiry(
        employee_id=employee.id, admin_id=admin.id, title=title,
        status=STATUS_WAITING, waiting_for=WAITING_FOR_ADMIN,
    )
    db.session.add(inquiry)
    db.session.flush()

    message = Message(inquiry_id=inquiry.id, sender_id=employee.id, content=content)
    db.session.add(message)
    db.session.flush()
    if files:
        save_attachments(message, files)
    db.session.commit()
    return inquiry


def _require_open(inquiry):
    if inquiry.is_deleted:
        raise InquiryError("삭제된 문의입니다.")
    if inquiry.status in INACTIVE_STATUSES:
        raise InquiryError("종료되거나 취소된 문의에는 메시지를 보낼 수 없습니다.")


def add_employee_message(inquiry, employee, content, files=None):
    if inquiry.employee_id != employee.id:
        raise InquiryError("본인의 문의가 아닙니다.")
    _require_open(inquiry)

    message = Message(inquiry_id=inquiry.id, sender_id=employee.id, content=content)
    db.session.add(message)
    db.session.flush()
    if files:
        save_attachments(message, files)

    if inquiry.status == STATUS_WAITING:
        inquiry.status = STATUS_ACTIVE
    inquiry.waiting_for = WAITING_FOR_ADMIN
    db.session.commit()


def add_admin_message(inquiry, admin, content, files=None):
    if inquiry.admin_id != admin.id:
        raise InquiryError("담당 관리자가 아닙니다.")
    _require_open(inquiry)

    message = Message(inquiry_id=inquiry.id, sender_id=admin.id, content=content)
    db.session.add(message)
    db.session.flush()
    if files:
        save_attachments(message, files)

    inquiry.status = STATUS_ACTIVE
    inquiry.waiting_for = WAITING_FOR_EMPLOYEE
    db.session.commit()


def mark_read_by_admin(inquiry, admin):
    """Call only when the admin actually opens the inquiry DETAIL page --
    never from the list view."""
    if inquiry.admin_id != admin.id:
        raise InquiryError("담당 관리자가 아닙니다.")
    if not inquiry.is_read:
        inquiry.is_read = True
        inquiry.read_at = datetime.utcnow()
        if inquiry.status == STATUS_WAITING:
            inquiry.status = STATUS_ACTIVE
        db.session.commit()


def close_inquiry(inquiry, admin):
    if inquiry.admin_id != admin.id:
        raise InquiryError("담당 관리자가 아닙니다.")
    inquiry.status = STATUS_CLOSED
    inquiry.waiting_for = WAITING_FOR_NONE
    inquiry.closed_at = datetime.utcnow()
    db.session.commit()


def delete_by_employee(inquiry, employee):
    """Immediate self-delete -- only available before the admin has read
    the conversation at all."""
    if inquiry.employee_id != employee.id:
        raise InquiryError("본인의 문의가 아닙니다.")
    if not inquiry.can_employee_delete:
        raise InquiryError("관리자가 이미 확인한 문의입니다. 삭제 요청 후 관리자 승인을 받아주세요.")

    inquiry.is_deleted = True
    inquiry.deleted_at = datetime.utcnow()
    inquiry.deleted_by = employee.id
    db.session.commit()


def request_delete(inquiry, employee, reason=None):
    """After the admin has read a conversation, the employee can only
    request deletion -- approving it is what actually cancels it."""
    if inquiry.employee_id != employee.id:
        raise InquiryError("본인의 문의가 아닙니다.")
    if not inquiry.can_request_delete:
        raise InquiryError("삭제를 요청할 수 없는 상태입니다.")

    inquiry.delete_requested = True
    inquiry.delete_requested_at = datetime.utcnow()
    inquiry.delete_requested_by = employee.id
    if reason:
        inquiry.cancel_reason = reason
    db.session.commit()


def approve_delete(inquiry, admin):
    """Approving a pending delete request finalizes the conversation as
    CANCELLED -- distinct from a normally-CLOSED conversation."""
    if inquiry.admin_id != admin.id:
        raise InquiryError("담당 관리자가 아닙니다.")
    if inquiry.is_deleted or inquiry.status in INACTIVE_STATUSES:
        raise InquiryError("이미 종료되었거나 삭제된 문의입니다.")
    if not inquiry.delete_requested:
        raise InquiryError("임직원이 삭제를 요청하지 않았습니다.")

    inquiry.delete_approved = True
    inquiry.delete_approved_at = datetime.utcnow()
    inquiry.delete_approved_by = admin.id
    inquiry.status = STATUS_CANCELLED
    inquiry.waiting_for = WAITING_FOR_NONE
    inquiry.cancelled_at = datetime.utcnow()
    inquiry.cancelled_by = admin.id
    db.session.commit()
