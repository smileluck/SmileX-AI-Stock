from fastapi import APIRouter

from app.services.llm import test_connection

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/proxy/status")
def proxy_status():
    return test_connection()


@router.post("/proxy/test")
def proxy_test():
    return test_connection()
