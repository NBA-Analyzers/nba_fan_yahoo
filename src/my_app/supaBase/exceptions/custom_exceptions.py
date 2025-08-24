class DatabaseError(Exception):
    """Raised when database operations fail"""
    pass

class ValidationError(Exception):
    """Raised when data validation fails"""
    pass

class NotFoundError(Exception):
    """Raised when requested resource is not found"""
    pass

class AuthenticationError(Exception):
    """Raised when authentication fails"""
    pass

class DuplicateError(Exception):
    """Raised when trying to create duplicate records"""
    pass