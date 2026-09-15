"""Core business rules for the one-active-inquiry-per-employee policy.

Every check here runs regardless of what the UI shows -- these functions
are the actual gate, called from the routes, so a direct POST/DELETE that
skips the HTML forms is still blocked (spec section 19).
"""

from datetime import datetime

from app.extensions import db
from app.models import (
    Inquiry,
    Message,
    ROLE_ADMIN,
    STATUS_ANSWERED,
    STATUS_CLOSED,
    STATUS_READ,
    STATUS_WAITING,
    WAITING_FOR_ADMIN,
    WAITING_FOR_EMPLOYEE,
    WAITING_FOR_NONE,
)


class InquiryError(Exception):
    """Raised when a requested action is not allowed by the business rules."""


def get_active_inquiry(employee_id):
    return Inquiry.query.filter(
        Inquiry.employee_id == employee_id,
        Inquiry.is_deleted.is_(False),
        Inquiry.status != STATUS_CLOSED,
    ).first()


def create_inquiry(employee, admin, title, content):
    if get_active_inquiry(employee.id):
        raise InquiryError("이미 처리 중인 문의가 있어 다른 관리자에게 새로운 문의를 보낼 수 없습니다.")

    inquiry = Inquiry(
        employee_id=employee.id, admin_id=admin.id, title=title,
        status=STATUS_WAITING, waiting_for=WAITING_FOR_ADMIN,
    )
    db.session.add(inquiry)
    db.session.flush()

    db.session.add(Message(inquiry_id=inquiry.id, sender_id=employee.id, content=content))
    db.session.commit()
    return inquiry


def add_employee_message(inquiry, employee, content):
    if inquiry.employee_id != employee.id:
        raise InquiryError("본인의 문의가 아닙니다.")
    if inquiry.is_deleted:
        raise InquiryError("삭제된 문의입니다.")
    if inquiry.status == STATUS_CLOSED:
        raise InquiryError("종료된 문의에는 메시지를 보낼 수 없습니다.")

    db.session.add(Message(inquiry_id=inquiry.id, sender_id=employee.id, content=content))
    # the employee is following up, so the admin owes a reply again --
    # but is_read is a one-way "has the admin ever opened this" flag and
    # must not be reset here (that's what keeps the delete policy simple).
    inquiry.status = STATUS_WAITING
    inquiry.waiting_for = WAITING_FOR_ADMIN
    db.session.commit()


def add_admin_message(inquiry, admin, content):
    if inquiry.admin_id != admin.id:
        raise InquiryError("담당 관리자가 아닙니다.")
    if inquiry.is_deleted:
        raise InquiryError("삭제된 문의입니다.")
    if inquiry.status == STATUS_CLOSED:
        raise InquiryError("종료된 문의에는 메시지를 보낼 수 없습니다.")

    db.session.add(Message(inquiry_id=inquiry.id, sender_id=admin.id, content=content))
    inquiry.status = STATUS_ANSWERED
    inquiry.waiting_for = WAITING_FOR_EMPLOYEE
    db.session.commit()


def mark_read_by_admin(inquiry, admin):
    """Call only when the admin actually opens the inquiry DETAIL page --
    never from the list view (spec section 14)."""
    if inquiry.admin_id != admin.id:
        raise InquiryError("담당 관리자가 아닙니다.")
    if not inquiry.is_read:
        inquiry.is_read = True
        inquiry.read_at = datetime.utcnow()
        if inquiry.status == STATUS_WAITING:
            inquiry.status = STATUS_READ
        db.session.commit()


def approve_delete(inquiry, admin):
    if inquiry.admin_id != admin.id:
        raise InquiryError("담당 관리자가 아닙니다.")
    if inquiry.is_deleted:
        raise InquiryError("이미 삭제된 문의입니다.")
    inquiry.delete_approved = True
    db.session.commit()


def close_inquiry(inquiry, admin):
    if inquiry.admin_id != admin.id:
        raise InquiryError("담당 관리자가 아닙니다.")
    inquiry.status = STATUS_CLOSED
    inquiry.waiting_for = WAITING_FOR_NONE
    inquiry.closed_at = datetime.utcnow()
    db.session.commit()


def delete_by_employee(inquiry, employee):
    if inquiry.employee_id != employee.id:
        raise InquiryError("본인의 문의가 아닙니다.")
    if not inquiry.can_employee_delete:
        raise InquiryError("관리자가 이미 확인한 문의입니다. 삭제하려면 관리자 승인이 필요합니다.")

    inquiry.is_deleted = True
    inquiry.deleted_at = datetime.utcnow()
    inquiry.deleted_by = employee.id
    db.session.commit()
