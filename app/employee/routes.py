import io

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app.config_values import STATUS_DOTS, STATUS_LABELS as ADMIN_STATUS_LABELS
from app.models import ROLE_ADMIN, STATUS_CLOSED, STATUS_LABELS, Attachment, Inquiry, User
from app.services.attachments import AttachmentError, can_access
from app.services.inquiries import (
    InquiryError,
    add_employee_message,
    create_inquiry,
    delete_by_employee,
    get_active_inquiry,
    request_delete,
)
from app.services.waiting import admins_with_status

employee_bp = Blueprint("employee", __name__, url_prefix="/me")


@employee_bp.before_request
@login_required
def _require_login():
    if current_user.is_admin:
        abort(403)


@employee_bp.context_processor
def inject_sidebar_data():
    """Powers the persistent left sidebar (my info / admin list / my
    conversations) on every employee page, without every route needing to
    pass it explicitly."""
    if not current_user.is_authenticated or current_user.is_admin:
        return {}
    history = (
        Inquiry.query.filter_by(employee_id=current_user.id, is_deleted=False, status=STATUS_CLOSED)
        .order_by(Inquiry.closed_at.desc())
        .all()
    )
    return dict(
        sidebar_active=get_active_inquiry(current_user.id),
        sidebar_history=history,
        sidebar_admin_rows=admins_with_status(),
        sidebar_status_dots=STATUS_DOTS,
    )


@employee_bp.route("/")
def home():
    active = get_active_inquiry(current_user.id)
    return render_template("employee/home.html", active=active, status_labels=STATUS_LABELS)


@employee_bp.route("/inquiries/new", methods=["GET", "POST"])
def new_inquiry():
    active = get_active_inquiry(current_user.id)

    if request.method == "POST":
        if active:
            flash("현재 처리 중인 문의가 있어 새로운 문의를 보낼 수 없습니다.")
            return redirect(url_for("employee.new_inquiry"))

        admin_id = request.form.get("admin_id", type=int)
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        files = request.files.getlist("attachments")
        admin = User.query.filter_by(id=admin_id, role=ROLE_ADMIN).first()

        if not admin or not title or not content:
            flash("관리자, 제목, 문의 내용을 모두 입력해주세요.")
            return redirect(url_for("employee.new_inquiry"))

        try:
            inquiry = create_inquiry(current_user, admin, title, content, files=files)
        except (InquiryError, AttachmentError) as e:
            flash(str(e))
            return redirect(url_for("employee.new_inquiry"))

        return redirect(url_for("employee.inquiry_detail", inquiry_id=inquiry.id))

    selected_admin = None
    admin_id = request.args.get("admin_id", type=int)
    if admin_id:
        selected_admin = User.query.filter_by(id=admin_id, role=ROLE_ADMIN).first()

    return render_template(
        "employee/new_inquiry.html",
        active=active,
        selected_admin=selected_admin,
        admin_rows=admins_with_status(),
        status_labels=STATUS_LABELS,
        admin_status_dots=STATUS_DOTS,
        admin_status_labels=ADMIN_STATUS_LABELS,
    )


@employee_bp.route("/inquiries/<int:inquiry_id>")
def inquiry_detail(inquiry_id):
    inquiry = Inquiry.query.filter_by(id=inquiry_id, employee_id=current_user.id, is_deleted=False).first_or_404()
    return render_template("employee/inquiry_detail.html", inquiry=inquiry, status_labels=STATUS_LABELS)


@employee_bp.route("/inquiries/<int:inquiry_id>/messages", methods=["POST"])
def send_message(inquiry_id):
    inquiry = Inquiry.query.filter_by(id=inquiry_id, employee_id=current_user.id, is_deleted=False).first_or_404()
    content = request.form.get("content", "").strip()
    files = request.files.getlist("attachments")
    if content or any(f.filename for f in files):
        try:
            add_employee_message(inquiry, current_user, content or "(첨부파일)", files=files)
        except (InquiryError, AttachmentError) as e:
            flash(str(e))
    return redirect(url_for("employee.inquiry_detail", inquiry_id=inquiry.id))


@employee_bp.route("/inquiries/<int:inquiry_id>/delete", methods=["POST"])
def delete_inquiry(inquiry_id):
    inquiry = Inquiry.query.filter_by(id=inquiry_id, employee_id=current_user.id, is_deleted=False).first_or_404()
    try:
        delete_by_employee(inquiry, current_user)
        flash("문의가 삭제되었습니다. 이제 다른 관리자에게 새 문의를 보낼 수 있습니다.")
        return redirect(url_for("employee.home"))
    except InquiryError as e:
        flash(str(e))
        return redirect(url_for("employee.inquiry_detail", inquiry_id=inquiry.id))


@employee_bp.route("/inquiries/<int:inquiry_id>/request-delete", methods=["POST"])
def request_delete_inquiry(inquiry_id):
    inquiry = Inquiry.query.filter_by(id=inquiry_id, employee_id=current_user.id, is_deleted=False).first_or_404()
    try:
        request_delete(inquiry, current_user)
        flash("삭제를 요청했습니다. 관리자 승인 후 처리됩니다.")
    except InquiryError as e:
        flash(str(e))
    return redirect(url_for("employee.inquiry_detail", inquiry_id=inquiry.id))


@employee_bp.route("/attachments/<int:attachment_id>")
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
