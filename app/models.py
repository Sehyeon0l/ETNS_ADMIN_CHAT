from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db

ROLE_ADMIN = "ADMIN"
ROLE_EMPLOYEE = "EMPLOYEE"

STATUS_WAITING = "WAITING"
STATUS_ACTIVE = "ACTIVE"
STATUS_CLOSED = "CLOSED"
STATUS_CANCELLED = "CANCELLED"

STATUS_LABELS = {
    STATUS_WAITING: "답변 대기",
    STATUS_ACTIVE: "처리 중",
    STATUS_CLOSED: "문의 종료",
    STATUS_CANCELLED: "문의 취소 완료",
}

# who currently owes the next reply -- independent of `status`, this is
# what admin workload (waiting-count) is actually computed from
WAITING_FOR_ADMIN = "ADMIN"
WAITING_FOR_EMPLOYEE = "EMPLOYEE"
WAITING_FOR_NONE = "NONE"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    employee_number = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_EMPLOYEE)
    department = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_admin(self):
        return self.role == ROLE_ADMIN


class Inquiry(db.Model):
    __tablename__ = "inquiries"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_WAITING)
    waiting_for = db.Column(db.String(20), nullable=False, default=WAITING_FOR_ADMIN)

    is_read = db.Column(db.Boolean, nullable=False, default=False)
    read_at = db.Column(db.DateTime)

    # employee-initiated delete request (only reachable once is_read is True)
    delete_requested = db.Column(db.Boolean, nullable=False, default=False)
    delete_requested_at = db.Column(db.DateTime)
    delete_requested_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    # admin approval of that request -- approving directly finalizes CANCELLED
    delete_approved = db.Column(db.Boolean, nullable=False, default=False)
    delete_approved_at = db.Column(db.DateTime)
    delete_approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    cancelled_at = db.Column(db.DateTime)
    cancelled_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    cancel_reason = db.Column(db.String(255))

    # is_deleted is a separate soft-delete flag -- only ever set by the
    # employee's *immediate* self-delete path (before the admin has read it).
    # CANCELLED conversations are hidden from the employee's own lists by
    # their status, not by is_deleted.
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    deleted_at = db.Column(db.DateTime)
    deleted_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = db.Column(db.DateTime)

    employee = db.relationship("User", foreign_keys=[employee_id])
    admin = db.relationship("User", foreign_keys=[admin_id])
    messages = db.relationship(
        "Message", backref="inquiry", order_by="Message.created_at", cascade="all, delete-orphan"
    )

    @property
    def can_employee_delete(self):
        """Immediate self-delete -- only before the admin has ever read it."""
        return not self.is_deleted and not self.is_read and self.status not in (STATUS_CLOSED, STATUS_CANCELLED)

    @property
    def can_request_delete(self):
        """Once read, the employee can only *request* deletion."""
        return (
            not self.is_deleted
            and self.is_read
            and not self.delete_requested
            and self.status not in (STATUS_CLOSED, STATUS_CANCELLED)
        )


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    inquiry_id = db.Column(db.Integer, db.ForeignKey("inquiries.id"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    read_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)

    sender = db.relationship("User")
    attachments = db.relationship("Attachment", backref="message", cascade="all, delete-orphan")


class Attachment(db.Model):
    __tablename__ = "attachments"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id"), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    # Vercel's filesystem is ephemeral, so the file itself is kept in the
    # database rather than on disk -- fine at MVP scale given MAX_FILE_SIZE.
    file_data = db.Column(db.LargeBinary, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
