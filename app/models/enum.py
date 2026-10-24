from enum import Enum


class UserRole(str, Enum):
    CUSTOMER = "customer"
    OWNER = "owner"
    ADMIN = "admin"


class OtpPurpose(str, Enum):
    REGISTER = "REGISTER"
    RESET_PASSWORD = "RESET_PASSWORD"


class TeamRole(str, Enum):
    LEADER = "LEADER"
    VICE_LEADER = "VICE_LEADER"
    TREASURER = "TREASURER"
    MEMBER = "MEMBER"



class TeamMemberStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PENDING = "PENDING"


class SportType(str, Enum):
    FOOTBALL = "FOOTBALL"


class PitchType(str, Enum):
    PITCH_5 = "PITCH_5"
    PITCH_7 = "PITCH_7"
    PITCH_11 = "PITCH_11"