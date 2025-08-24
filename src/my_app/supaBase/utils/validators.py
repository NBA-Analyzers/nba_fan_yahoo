
import re
from exceptions.custom_exceptions import ValidationError

def validate_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        raise ValidationError("Invalid email format")
    return True

def validate_required_fields(data: dict, required_fields: list) -> bool:
    missing_fields = [field for field in required_fields if not data.get(field)]
    if missing_fields:
        raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")
    return True

def validate_platform(platform: str) -> bool:
    allowed_platforms = ["yahoo", "espn"]  # Future-ready
    if platform.lower() not in allowed_platforms:
        raise ValidationError(f"Invalid platform. Allowed: {', '.join(allowed_platforms)}")
    return True