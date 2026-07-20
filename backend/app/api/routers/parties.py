from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import require
from app.db.session import get_db
from app.models.party import Customer, Vendor
from app.models.user import User
from app.schemas import CustomerIn, CustomerOut, VendorIn, VendorOut

router = APIRouter(prefix="/api", tags=["parties"])


@router.get("/vendors", response_model=list[VendorOut])
def list_vendors(user: User = Depends(require("vendor:read")), db: Session = Depends(get_db)):
    return db.scalars(
        select(Vendor).where(Vendor.org_id == user.org_id).order_by(Vendor.name)
    ).all()


@router.post("/vendors", response_model=VendorOut, status_code=201)
def create_vendor(
    body: VendorIn, user: User = Depends(require("vendor:create")),
    db: Session = Depends(get_db),
):
    v = Vendor(org_id=user.org_id, **body.model_dump())
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


@router.get("/customers", response_model=list[CustomerOut])
def list_customers(user: User = Depends(require("customer:read")), db: Session = Depends(get_db)):
    return db.scalars(
        select(Customer).where(Customer.org_id == user.org_id).order_by(Customer.name)
    ).all()


@router.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(
    body: CustomerIn, user: User = Depends(require("customer:create")),
    db: Session = Depends(get_db),
):
    c = Customer(org_id=user.org_id, **body.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c
