from app.modules.assessment.router import router as tests_router
from app.modules.academics.router import router as academics_router
from app.modules.admin.router import router as admin_router
from app.modules.auth.router import router as auth_router
from app.modules.crm.router import router as crm_router
from app.modules.finance.payments import router as payments_router
from app.modules.inbox.router import router as inbox_router
from app.modules.org.router import router as org_router
from app.modules.students.router import router as students_router

ROUTERS = [auth_router, admin_router, org_router, students_router, academics_router, payments_router, crm_router, inbox_router, tests_router]
