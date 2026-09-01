"""transaction 层路由：/api/transaction（操作记录 list，只读审计，body 传分页/排序）。"""
from fastapi import APIRouter, Depends

from ..deps import get_current_user, get_transaction_service
from ..schemas import TransactionListIn
from ..service.transaction_service import TransactionService

router = APIRouter(prefix="/api/transaction", tags=["transaction"])


@router.post("/list")
def list_operations(body: TransactionListIn, user: dict = Depends(get_current_user),
                    svc: TransactionService = Depends(get_transaction_service)) -> dict:
    return svc.list(user["user_id"], page=body.page, page_size=body.page_size, sort=body.sort)
