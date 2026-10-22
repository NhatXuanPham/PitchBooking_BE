from enum import Enum


class UserRole(str, Enum):
    CUSTOMER = "customer"
    OWNER = "owner"
    ADMIN = "admin"


class OtpPurpose(str, Enum):
    REGISTER = "REGISTER"
    RESET_PASSWORD = "RESET_PASSWORD"