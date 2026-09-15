"""Attachment upload validation and access control.

Files are stored as bytes in Postgres (not on disk) since Vercel's
serverless filesystem is ephemeral -- see Attachment.file_data. Every
access still goes through validate_upload() and can_access(), so the
security requirements (extension + MIME whitelist, size cap, randomized
name, participant-only access) hold regardless of where the bytes live.
"""

import mimetypes
import uuid

from werkzeug.utils import secure_filename

from app.config_values import ALLOWED_FILE_EXTENSIONS, MAX_FILE_SIZE
from app.extensions import db
from app.models import Attachment


class AttachmentError(Exception):
    pass


def _extension_of(filename):
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def validate_upload(file_storage):
    filename = secure_filename(file_storage.filename or "")
    if not filename:
        raise AttachmentError("파일 이름을 확인할 수 없습니다.")

    ext = _extension_of(filename)
    if ext not in ALLOWED_FILE_EXTENSIONS:
        raise AttachmentError(f"허용되지 않는 파일 형식입니다 (.{ext}).")

    data = file_storage.read()
    if len(data) > MAX_FILE_SIZE:
        raise AttachmentError(f"파일 크기가 너무 큽니다 (최대 {MAX_FILE_SIZE // (1024 * 1024)}MB).")
    if not data:
        raise AttachmentError("빈 파일은 첨부할 수 없습니다.")

    mime_type = file_storage.mimetype or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    return {
        "original_filename": filename,
        "stored_filename": f"{uuid.uuid4().hex}.{ext}",
        "file_size": len(data),
        "mime_type": mime_type,
        "file_data": data,
    }


def save_attachments(message, file_storages):
    for file_storage in file_storages:
        if not file_storage or not file_storage.filename:
            continue
        info = validate_upload(file_storage)
        db.session.add(Attachment(message_id=message.id, **info))
    db.session.commit()


def can_access(attachment, user):
    """Only participants of the attachment's conversation may view/download
    it -- checked here regardless of role, so an unrelated admin can't pull
    another admin's files either."""
    inquiry = attachment.message.inquiry
    return user.id in (inquiry.employee_id, inquiry.admin_id)
