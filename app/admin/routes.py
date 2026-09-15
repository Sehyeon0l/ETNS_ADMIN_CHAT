from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.config_values import STATUS_DOTS, STATUS_LABELS as WORKLOAD_LABELS
from app.models import Inquiry, STATUS_ANSWERED, STATUS_CLOSED, STATUS_LABELS, STATUS_READ, STATUS_WAITING
from app.services.inquiries import InquiryError, add_admin_message, approve_delete, close_inquiry, mark_read_by_admin
from app.services.waiting import waiting_count_for_admin
from app.config_values import compute_admin_status

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
@login_required
def _require_admin():
    if not current_user.is_admin:
        abort(403)


@admin_bp.route("/")
def dashboard():
    show_deleted = request.args.get("deleted") == "1"

    if show_deleted:
        deleted_inquiries = (
            Inquiry.query.filter_by(admin_id=current_user.id, is_deleted=True)
            .order_by(Inquiry.updated_at.desc())
            .all()
        )
        active_inquiries = []
        closed_inquiries = []
    else:
        deleted_inquiries = []
        active_inquiries = (
            Inquiry.query.filter(
                Inquiry.admin_id == current_user.id,
                Inquiry.is_deleted.is_(False),
                Inquiry.status != STATUS_CLOSED,
            )
            .order_by(Inquiry.updated_at.desc())
            .all()
        )
        closed_inquiries = (
            Inquiry.query.filter_by(admin_id=current_user.id, is_deleted=False, status=STATUS_CLOSED)
            .order_by(Inquiry.closed_at.desc())
            .all()
        )

    all_active = Inquiry.query.filter_by(admin_id=current_user.id, is_deleted=False).all()
    counts = {
        "total": len(all_active),
        "unread": sum(1 for i in all_active if not i.is_read),
        "waiting_or_read": sum(1 for i in all_active if i.status in (STATUS_WAITING, STATUS_READ)),
        "answered": sum(1 for i in all_active if i.status == STATUS_ANSWERED),
        "closed": sum(1 for i in all_active if i.status == STATUS_CLOSED),
    }

    my_waiting_count = waiting_count_for_admin(current_user.id)
    my_status = compute_admin_status(my_waiting_count)

    return render_template(
        "admin/dashboard.html",
        active_inquiries=active_inquiries,
        closed_inquiries=closed_inquiries,
        deleted_inquiries=deleted_inquiries,
        counts=counts,
        show_deleted=show_deleted,
        status_labels=STATUS_LABELS,
        my_waiting_count=my_waiting_count,
        my_status=my_status,
        my_status_dot=STATUS_DOTS[my_status],
        my_status_label=WORKLOAD_LABELS[my_status],
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
