from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models import Inquiry, STATUS_ANSWERED, STATUS_CLOSED, STATUS_LABELS, STATUS_READ, STATUS_WAITING
from app.services.inquiries import InquiryError, add_admin_message, approve_delete, close_inquiry, mark_read_by_admin

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
@login_required
def _require_admin():
    if not current_user.is_admin:
        abort(403)


@admin_bp.route("/")
def dashboard():
    show_deleted = request.args.get("deleted") == "1"

    base_query = Inquiry.query.filter_by(admin_id=current_user.id)
    if show_deleted:
        inquiries = base_query.filter_by(is_deleted=True).order_by(Inquiry.updated_at.desc()).all()
    else:
        inquiries = base_query.filter_by(is_deleted=False).order_by(Inquiry.updated_at.desc()).all()

    all_active = Inquiry.query.filter_by(admin_id=current_user.id, is_deleted=False).all()
    counts = {
        "total": len(all_active),
        "unread": sum(1 for i in all_active if not i.is_read),
        "waiting_or_read": sum(1 for i in all_active if i.status in (STATUS_WAITING, STATUS_READ)),
        "answered": sum(1 for i in all_active if i.status == STATUS_ANSWERED),
        "closed": sum(1 for i in all_active if i.status == STATUS_CLOSED),
    }

    return render_template(
        "admin/dashboard.html",
        inquiries=inquiries,
        counts=counts,
        show_deleted=show_deleted,
        status_labels=STATUS_LABELS,
    )


@admin_bp.route("/inquiries/<int:inquiry_id>")
def inquiry_detail(inquiry_id):
    inquiry = Inquiry.query.filter_by(id=inquiry_id, admin_id=current_user.id).first_or_404()
    mark_read_by_admin(inquiry, current_user)
    return render_template("admin/inquiry_detail.html", inquiry=inquiry, status_labels=STATUS_LABELS)


@admin_bp.route("/inquiries/<int:inquiry_id>/messages", methods=["POST"])
def send_message(inquiry_id):
    inquiry = Inquiry.query.filter_by(id=inquiry_id, admin_id=current_user.id).first_or_404()
    content = request.form.get("content", "").strip()
    if content:
        try:
            add_admin_message(inquiry, current_user, content)
        except InquiryError as e:
            flash(str(e))
    return redirect(url_for("admin.inquiry_detail", inquiry_id=inquiry.id))


@admin_bp.route("/inquiries/<int:inquiry_id>/approve-delete", methods=["POST"])
def approve_delete_route(inquiry_id):
    inquiry = Inquiry.query.filter_by(id=inquiry_id, admin_id=current_user.id).first_or_404()
    try:
        approve_delete(inquiry, current_user)
        flash("삭제를 승인했습니다.")
    except InquiryError as e:
        flash(str(e))
    return redirect(url_for("admin.inquiry_detail", inquiry_id=inquiry.id))


@admin_bp.route("/inquiries/<int:inquiry_id>/close", methods=["POST"])
def close_inquiry_route(inquiry_id):
    inquiry = Inquiry.query.filter_by(id=inquiry_id, admin_id=current_user.id).first_or_404()
    close_inquiry(inquiry, current_user)
    flash("문의를 종료했습니다.")
    return redirect(url_for("admin.inquiry_detail", inquiry_id=inquiry.id))
