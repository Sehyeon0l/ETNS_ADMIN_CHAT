from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db

ROLE_ADMIN = "ADMIN"
ROLE_EMPLOYEE = "EMPLOYEE"

STATUS_WAITING = "WAITING"
STATUS_READ = "READ"
STATUS_ANSWERED = "ANSWERED"
STATUS_CLOSED = "CLOSED"

STATUS_LABELS = {
    STATUS_WAITING: "답변 대기",
    STATUS_READ: "처리 중",
    STATUS_ANSWERED: "답변 완료",
    STATUS_CLOSED: "문의 종료",
}


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    employee_number = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_EMPLOYEE)
    department = db.Column(db.String(50))
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

    is_read = db.Column(db.Boolean, nullable=False, default=False)
    read_at = db.Column(db.DateTime)
    delete_approved = db.Column(db.Boolean, nullable=False, default=False)

    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    deleted_at = db.Column(db.DateTime)
    deleted_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    employee = db.relationship("User", foreign_keys=[employee_id])
    admin = db.relationship("User", foreign_keys=[admin_id])
    messages = db.relationship(
        "Message", backref="inquiry", order_by="Message.created_at", cascade="all, delete-orphan"
    )

    @property
    def can_employee_delete(self):
        if self.is_deleted:
            return False
        if not self.is_read:
            return True
        return self.delete_approved


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
