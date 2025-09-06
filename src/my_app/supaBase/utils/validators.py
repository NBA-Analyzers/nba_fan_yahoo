# validators.py
import re

from ..exceptions.custom_exceptions import ValidationError


def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        raise ValidationError("Invalid email format")
    return True

def validate_required_fields(data: dict, required_fields: list) -> bool:
    """Validate that all required fields are present and not empty"""
    missing_fields = [field for field in required_fields if not data.get(field)]
    if missing_fields:
        raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")
    return True

def validate_platform(platform: str) -> bool:
    """Validate fantasy platform"""
    if not platform:
        raise ValidationError("Platform cannot be empty")
    
    allowed_platforms = ["yahoo", "espn"]  # Future-ready
    if platform.lower() not in allowed_platforms:

        raise ValidationError(f"Invalid platform '{platform}'. Allowed: {', '.join(allowed_platforms)}")
    return True

def validate_user_id(user_id: str, platform: str = None) -> bool:
    """Validate user ID format"""
    if not user_id or not user_id.strip():
        raise ValidationError(f"User ID cannot be empty{' for ' + platform if platform else ''}")
    return True


