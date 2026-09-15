from datetime import datetime

from app import create_app
from app.extensions import db
from app.models import Inquiry, Message, ROLE_ADMIN, ROLE_EMPLOYEE, STATUS_CLOSED, STATUS_READ, STATUS_WAITING, User

app = create_app()

with app.app_context():
    db.create_all()

    admins = [
        ("A0001", "김관리자", "kim.admin@etns.com", "총무팀"),
        ("A0002", "이관리자", "lee.admin@etns.com", "인사팀"),
    ]
    admin_users = {}
    for emp_no, name, email, dept in admins:
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(employee_number=emp_no, name=name, email=email, role=ROLE_ADMIN, department=dept)
            user.set_password("admin1234")
            db.session.add(user)
            db.session.commit()
        admin_users[name] = user

    employees = [
        ("E1001", "홍길동", "hong@etns.com"),
        ("E1002", "김민준", "kim@etns.com"),
        ("E1003", "이서연", "lee@etns.com"),
        ("E1004", "박지훈", "park@etns.com"),
    ]
    employee_users = {}
    for emp_no, name, email in employees:
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(employee_number=emp_no, name=name, email=email, role=ROLE_EMPLOYEE)
            user.set_password("demo1234")
            db.session.add(user)
            db.session.commit()
        employee_users[name] = user

    def ensure_inquiry(employee_name, admin_name, title, first_message, **overrides):
        employee = employee_users[employee_name]
        admin = admin_users[admin_name]
        existing = Inquiry.query.filter_by(employee_id=employee.id, admin_id=admin.id, title=title).first()
        if existing:
            return existing
        inquiry = Inquiry(employee_id=employee.id, admin_id=admin.id, title=title, status=STATUS_WAITING)
        for k, v in overrides.items():
            setattr(inquiry, k, v)
        db.session.add(inquiry)
        db.session.flush()
        db.session.add(Message(inquiry_id=inquiry.id, sender_id=employee.id, content=first_message))
        db.session.commit()
        return inquiry

    # 1) waiting, not read yet -> employee can delete immediately
    ensure_inquiry(
        "홍길동", "김관리자", "노트북 지급 문의",
        "신규 입사자용 노트북은 언제쯤 받을 수 있을까요?",
    )

    # 2) admin has read it, not approved -> employee cannot delete
    ensure_inquiry(
        "김민준", "이관리자", "연차 사용 문의",
        "다음 주 연차 사용 가능한지 확인 부탁드립니다.",
        status=STATUS_READ, is_read=True, read_at=datetime.utcnow(),
    )

    # 3) admin has read it AND approved deletion -> employee can delete now
    ensure_inquiry(
        "이서연", "김관리자", "비품 신청 문의",
        "모니터 거치대 추가로 신청하고 싶습니다.",
        status=STATUS_READ, is_read=True, read_at=datetime.utcnow(), delete_approved=True,
    )

    # 4) previous inquiry already closed -> no active inquiry, free to start a new one
    inq4 = ensure_inquiry(
        "박지훈", "이관리자", "출장비 정산 문의",
        "지난달 출장비 정산이 아직 안 된 것 같습니다.",
        status=STATUS_READ, is_read=True, read_at=datetime.utcnow(),
    )
    if inq4.status != STATUS_CLOSED:
        db.session.add(Message(inquiry_id=inq4.id, sender_id=admin_users["이관리자"].id, content="확인 후 정산 완료했습니다. 감사합니다."))
        inq4.status = STATUS_CLOSED
        db.session.commit()

    print("Seed complete.")
    print("Admin logins (password: admin1234):")
    for emp_no, name, email, dept in admins:
        print(f"  {name} ({dept}) - {email}")
    print("Employee logins (password: demo1234):")
    for emp_no, name, email in employees:
        print(f"  {name} - {email}")
