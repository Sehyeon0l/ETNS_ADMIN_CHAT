from flask import Blueprint, abort, flash, redirect, render_template, request, url_for, send_file
import io

from flask_login import current_user, login_required

from app.config_values import STATUS_DOTS, STATUS_LABELS as WORKLOAD_LABELS, compute_admin_status
from app.extensions import db
from app.models import Attachment, Inquiry, ROLE_ADMIN, ROLE_EMPLOYEE, STATUS_CANCELLED, STATUS_CLOSED, STATUS_LABELS, User
from app.services.attachments import AttachmentError, can_access
from app.services.directory import employee_stats
from app.services.inquiries import (
    InquiryError,
    add_admin_message,
    approve_delete,
    close_inquiry,
    mark_read_by_admin,
)
from app.services.waiting import admins_with_status, waiting_count_for_admin

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
                Inquiry.status.notin_((STATUS_CLOSED, STATUS_CANCELLED)),
            )
            .order_by(Inquiry.updated_at.desc())
            .all()
        )
        closed_inquiries = (
            Inquiry.query.filter(
                Inquiry.admin_id == current_user.id,
                Inquiry.is_deleted.is_(False),
                Inquiry.status.in_((STATUS_CLOSED, STATUS_CANCELLED)),
            )
            .order_by(Inquiry.updated_at.desc())
            .all()
        )

    all_active = Inquiry.query.filter_by(admin_id=current_user.id, is_deleted=False).all()
    pending_delete_requests = Inquiry.query.filter_by(
        admin_id=current_user.id, delete_requested=True, delete_approved=False, is_deleted=False
    ).count()
    counts = {
        "total": len(all_active),
        "unread": sum(1 for i in all_active if not i.is_read),
        "waiting_or_read": sum(1 for i in all_active if i.status not in (STATUS_CLOSED, STATUS_CANCELLED)),
        "closed": sum(1 for i in all_active if i.status == STATUS_CLOSED),
        "cancelled": sum(1 for i in all_active if i.status == STATUS_CANCELLED),
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
        pending_delete_requests=pending_delete_requests,
    )


@admin_bp.route("/delete-requests")
def delete_requests():
    requests_ = (
        Inquiry.query.filter_by(admin_id=current_user.id, delete_requested=True, delete_approved=False, is_deleted=False)
        .order_by(Inquiry.delete_requested_at.desc())
        .all()
    )
    return render_template("admin/delete_requests.html", requests=requests_)


@admin_bp.route("/inquiries/<int:inquiry_id>")
def inquiry_detail(inquiry_id):
    inquiry = Inquiry.query.get_or_404(inquiry_id)
    is_owner = inquiry.admin_id == current_user.id
    if is_owner:
        mark_read_by_admin(inquiry, current_user)

    history = []
    history.append((inquiry.created_at, f"{inquiry.employee.name}님이 문의를 생성했습니다."))
    if inquiry.read_at:
        history.append((inquiry.read_at, f"{inquiry.admin.name}이(가) 문의를 확인했습니다."))
    if inquiry.delete_requested_at:
        history.append((inquiry.delete_requested_at, f"{inquiry.employee.name}님이 삭제를 요청했습니다."))
    if inquiry.delete_approved_at:
        history.append((inquiry.delete_approved_at, f"{inquiry.admin.name}이(가) 삭제를 승인했습니다."))
    if inquiry.closed_at:
        history.append((inquiry.closed_at, f"{inquiry.admin.name}이(가) 문의를 종료했습니다."))
    history.sort(key=lambda t: t[0])

    return render_template(
        "admin/inquiry_detail.html",
        inquiry=inquiry,
        status_labels=STATUS_LABELS,
        history=history,
        is_owner=is_owner,
    )


@admin_bp.route("/inquiries/<int:inquiry_id>/messages", methods=["POST"])
def send_message(inquiry_id):
    inquiry = Inquiry.query.filter_by(id=inquiry_id, admin_id=current_user.id).first_or_404()
    content = request.form.get("content", "").strip()
    files = request.files.getlist("attachments")
    if content or any(f.filename for f in files):
        try:
            add_admin_message(inquiry, current_user, content or "(첨부파일)", files=files)
        except (InquiryError, AttachmentError) as e:
            flash(str(e))
    return redirect(url_for("admin.inquiry_detail", inquiry_id=inquiry.id))


@admin_bp.route("/inquiries/<int:inquiry_id>/approve-delete", methods=["POST"])
def approve_delete_route(inquiry_id):
    inquiry = Inquiry.query.filter_by(id=inquiry_id, admin_id=current_user.id).first_or_404()
    try:
        approve_delete(inquiry, current_user)
        flash("삭제를 승인했습니다. 문의가 취소 처리되었습니다.")
    except InquiryError as e:
        flash(str(e))
    return redirect(url_for("admin.inquiry_detail", inquiry_id=inquiry.id))


@admin_bp.route("/inquiries/<int:inquiry_id>/close", methods=["POST"])
def close_inquiry_route(inquiry_id):
    inquiry = Inquiry.query.filter_by(id=inquiry_id, admin_id=current_user.id).first_or_404()
    close_inquiry(inquiry, current_user)
    flash("문의를 종료했습니다.")
    return redirect(url_for("admin.inquiry_detail", inquiry_id=inquiry.id))


@admin_bp.route("/attachments/<int:attachment_id>")
def download_attachment(attachment_id):
    attachment = Attachment.query.get_or_404(attachment_id)
    if not can_access(attachment, current_user):
        abort(403)
    return send_file(
        io.BytesIO(attachment.file_data),
        mimetype=attachment.mime_type,
        as_attachment=False,
        download_name=attachment.original_filename,
    )


# ---- employee management ----


@admin_bp.route("/users")
def users():
    q = request.args.get("q", "").strip()
    query = User.query.filter_by(role=ROLE_EMPLOYEE)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(User.name.ilike(like), User.employee_number.ilike(like), User.email.ilike(like)))
    employees = query.order_by(User.employee_number).all()

    rows = []
    for e in employees:
        active = employee_stats(e.id)["active"]
        rows.append({"user": e, "active": active})

    return render_template("admin/users.html", rows=rows, q=q)


@admin_bp.route("/users/<int:user_id>")
def user_detail(user_id):
    employee = User.query.filter_by(id=user_id, role=ROLE_EMPLOYEE).first_or_404()
    stats = employee_stats(employee.id)
    return render_template("admin/user_detail.html", employee=employee, stats=stats)


@admin_bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
def toggle_user_active(user_id):
    employee = User.query.filter_by(id=user_id, role=ROLE_EMPLOYEE).first_or_404()
    employee.is_active = not employee.is_active
    db.session.commit()
    flash(f"{employee.name}님의 계정을 {'활성화' if employee.is_active else '비활성화'}했습니다.")
    return redirect(url_for("admin.user_detail", user_id=employee.id))


# ---- manager (admin) management ----


@admin_bp.route("/managers")
def managers():
    q = request.args.get("q", "").strip()
    query = User.query.filter_by(role=ROLE_ADMIN)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(User.name.ilike(like), User.department.ilike(like)))
    admins = query.order_by(User.name).all()

    rows = admins_with_status()
    if q:
        wanted_ids = {a.id for a in admins}
        rows = [r for r in rows if r["user"].id in wanted_ids]

    return render_template("admin/managers.html", rows=rows, q=q, status_dots=STATUS_DOTS, status_labels=WORKLOAD_LABELS)


@admin_bp.route("/managers/<int:manager_id>")
def manager_detail(manager_id):
    manager = User.query.filter_by(id=manager_id, role=ROLE_ADMIN).first_or_404()
    waiting_count = waiting_count_for_admin(manager.id)
    status = compute_admin_status(waiting_count)
    conversations = Inquiry.query.filter_by(admin_id=manager.id, is_deleted=False).order_by(Inquiry.updated_at.desc()).all()
    return render_template(
        "admin/manager_detail.html",
        manager=manager,
        waiting_count=waiting_count,
        status=status,
        status_dot=STATUS_DOTS[status],
        status_label=WORKLOAD_LABELS[status],
        conversations=conversations,
        status_labels=STATUS_LABELS,
    )


@admin_bp.route("/managers/<int:manager_id>/toggle-active", methods=["POST"])
def toggle_manager_active(manager_id):
    manager = User.query.filter_by(id=manager_id, role=ROLE_ADMIN).first_or_404()
    manager.is_active = not manager.is_active
    db.session.commit()
    flash(f"{manager.name}의 계정을 {'활성화' if manager.is_active else '비활성화'}했습니다.")
    return redirect(url_for("admin.manager_detail", manager_id=manager.id))


@admin_bp.route("/managers/<int:manager_id>/password", methods=["POST"])
def change_manager_password(manager_id):
    manager = User.query.filter_by(id=manager_id, role=ROLE_ADMIN).first_or_404()
    new_password = request.form.get("new_password", "")
    if len(new_password) < 6:
        flash("비밀번호는 6자 이상이어야 합니다.")
    else:
        manager.set_password(new_password)
        db.session.commit()
        flash(f"{manager.name}의 비밀번호를 변경했습니다.")
    return redirect(url_for("admin.manager_detail", manager_id=manager.id))
