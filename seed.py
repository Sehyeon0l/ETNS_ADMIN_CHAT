from datetime import datetime

from app import create_app
from app.extensions import db
from app.models import Inquiry, Message, ROLE_ADMIN, ROLE_EMPLOYEE, STATUS_CLOSED, STATUS_READ, STATUS_WAITING, User

app = create_app()

DEPARTMENT = "연말정산TF"

with app.app_context():
    db.create_all()

    admin_names = ["관리자A", "관리자B", "관리자C", "관리자D", "관리자E", "관리자F", "관리자G"]
    admin_users = {}
    for i, name in enumerate(admin_names, start=1):
        emp_no = f"A{1000 + i}"
        email = f"admin{name[-1].lower()}@etns.com"
        user = User.query.filter_by(employee_number=emp_no).first()
        if not user:
            user = User(employee_number=emp_no, name=name, email=email, role=ROLE_ADMIN, department=DEPARTMENT)
            user.set_password("admin1234")
            db.session.add(user)
            db.session.commit()
        else:
            # keep name/department in sync if the seed definition changes
            user.name = name
            user.department = DEPARTMENT
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

    def ensure_inquiry(employee, admin, title, first_message, **overrides):
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

    # the 4 policy-test scenarios (unread/read/read+approved/closed), spread
    # across different admins so they also count toward those admins' totals
    ensure_inquiry(
        employee_users["홍길동"], admin_users["관리자A"], "노트북 지급 문의",
        "신규 입사자용 노트북은 언제쯤 받을 수 있을까요?",
    )
    ensure_inquiry(
        employee_users["김민준"], admin_users["관리자D"], "연차 사용 문의",
        "다음 주 연차 사용 가능한지 확인 부탁드립니다.",
        status=STATUS_READ, is_read=True, read_at=datetime.utcnow(),
    )
    ensure_inquiry(
        employee_users["이서연"], admin_users["관리자F"], "비품 신청 문의",
        "모니터 거치대 추가로 신청하고 싶습니다.",
        status=STATUS_READ, is_read=True, read_at=datetime.utcnow(), delete_approved=True,
    )
    closed = ensure_inquiry(
        employee_users["박지훈"], admin_users["관리자G"], "출장비 정산 문의",
        "지난달 출장비 정산이 아직 안 된 것 같습니다.",
        status=STATUS_READ, is_read=True, read_at=datetime.utcnow(),
    )
    if closed.status != STATUS_CLOSED:
        db.session.add(Message(inquiry_id=closed.id, sender_id=admin_users["관리자G"].id, content="확인 후 정산 완료했습니다. 감사합니다."))
        closed.status = STATUS_CLOSED
        db.session.commit()

    # fill the remaining waiting-count targets with synthetic employees, one
    # active (unread, WAITING) inquiry each -- matches the spec's example
    # dashboard numbers: A=1 B=0 C=4 D=2 E=8 F=3 G=7
    target_counts = {"관리자A": 1, "관리자B": 0, "관리자C": 4, "관리자D": 2, "관리자E": 8, "관리자F": 3, "관리자G": 7}
    already_counted = {"관리자A": 1, "관리자D": 1, "관리자F": 1}  # from the 4 named employees above

    synthetic_index = 1
    for admin_name, target in target_counts.items():
        remaining = target - already_counted.get(admin_name, 0)
        for _ in range(remaining):
            emp_no = f"S{2000 + synthetic_index}"
            name = f"임직원{synthetic_index:02d}"
            email = f"staff{synthetic_index:02d}@etns.com"
            user = User.query.filter_by(employee_number=emp_no).first()
            if not user:
                user = User(employee_number=emp_no, name=name, email=email, role=ROLE_EMPLOYEE)
                user.set_password("demo1234")
                db.session.add(user)
                db.session.commit()
            ensure_inquiry(
                user, admin_users[admin_name], "연말정산 서류 문의",
                "연말정산 서류 제출 방법이 궁금합니다.",
            )
            synthetic_index += 1

    print("Seed complete.")
    print("Admin logins (password: admin1234):")
    for name in admin_names:
        print(f"  {name} ({DEPARTMENT}) - {admin_users[name].email}")
    print("Employee logins (password: demo1234):")
    for emp_no, name, email in employees:
        print(f"  {name} - {email}")
    print(f"  + {synthetic_index - 1} synthetic staff accounts (staff01@etns.com .. , password: demo1234)")
