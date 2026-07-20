from datetime import date
from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ---- Auth ----
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    full_name: str
    org_id: int

    @property
    def role_name(self) -> str:  # populated in router
        return ""


class MeOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    org_id: int
    role: str
    permissions: list[str]


# ---- Accounts ----
class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    type: str
    parent_id: int | None
    is_postable: bool


class AccountBalanceOut(AccountOut):
    balance: float


# ---- Journal ----
class JournalLineIn(BaseModel):
    account_id: int
    debit: float = 0
    credit: float = 0
    description: str = ""


class JournalEntryIn(BaseModel):
    entry_date: date
    memo: str = ""
    lines: list[JournalLineIn] = Field(min_length=2)


class JournalLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    debit: float
    credit: float
    description: str


class JournalEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ref: str
    entry_date: date
    memo: str
    status: str
    source: str
    lines: list[JournalLineOut]


# ---- Parties ----
class VendorIn(BaseModel):
    name: str
    email: EmailStr | None = None
    gstin: str | None = None


class VendorOut(VendorIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ai_score: float


class CustomerIn(BaseModel):
    name: str
    email: EmailStr | None = None
    gstin: str | None = None
    credit_limit: float = 0


class CustomerOut(CustomerIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ai_default_risk: float


# ---- Invoices ----
class InvoiceLineIn(BaseModel):
    description: str = ""
    quantity: float = 1
    unit_price: float = 0
    tax_rate: float = 0
    account_id: int | None = None


class InvoiceIn(BaseModel):
    kind: str = Field(pattern="^(AR|AP)$")
    number: str
    vendor_id: int | None = None
    customer_id: int | None = None
    issue_date: date
    due_date: date
    lines: list[InvoiceLineIn] = Field(min_length=1)


class InvoiceLineOut(InvoiceLineIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    number: str
    vendor_id: int | None
    customer_id: int | None
    issue_date: date
    due_date: date
    subtotal: float
    tax_total: float
    total: float
    amount_paid: float
    status: str
    entry_mode: str
    tds_total: float
    journal_entry_id: int | None
    lines: list[InvoiceLineOut]


class PaymentIn(BaseModel):
    amount: float
    pay_date: date
    method: str = "bank"
    reference: str = ""


# ---- Bill ingestion & distribution ----
class BillDistributeIn(BaseModel):
    base: float | None = None
    gross: float | None = None
    gst_rate: float | None = None
    gst_amount: float | None = None
    tds_rate: float | None = None
    tds_amount: float | None = None
    description: str = ""


class BillItemIn(BaseModel):
    description: str = ""
    amount: float = 0


class ClassifyItemsIn(BaseModel):
    items: list[BillItemIn] = Field(min_length=1)
    tds_rate: float = 0
    tds_amount: float | None = None


class BillItemsPostIn(BaseModel):
    number: str
    vendor_id: int | None = None
    vendor_name: str | None = None
    vendor_gstin: str | None = None
    issue_date: date
    due_date: date
    entry_mode: str = Field(default="manual", pattern="^(manual|pdf|excel|csv|image|word)$")
    items: list[BillItemIn] = Field(min_length=1)
    tds_rate: float = 0
    tds_amount: float | None = None


class BillPostIn(BaseModel):
    number: str
    vendor_id: int | None = None
    vendor_name: str | None = None
    vendor_gstin: str | None = None
    issue_date: date
    due_date: date
    entry_mode: str = Field(default="manual", pattern="^(manual|pdf|excel|csv|image|word)$")
    description: str = ""
    base: float
    gst_amount: float = 0
    tds_amount: float = 0


# ---- AI ----
class ChatIn(BaseModel):
    question: str


class InvoiceReadIn(BaseModel):
    text: str


class ExpenseCategorizeIn(BaseModel):
    description: str
    amount: float | None = None


class FraudCheckIn(BaseModel):
    amount: float
    when: date | None = None
    vendor_id: int | None = None
    description: str = ""
