# custom_exceptions.py
class FantasyAppBaseException(Exception):
    """Base exception for the fantasy app"""
    pass

class ValidationError(FantasyAppBaseException):
    """Raised when validation fails"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class NotFoundError(FantasyAppBaseException):
    """Raised when a requested resource is not found"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class DuplicateError(FantasyAppBaseException):
    """Raised when trying to create a duplicate resource"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class DatabaseError(FantasyAppBaseException):
    """Raised when database operations fail"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class AuthenticationError(FantasyAppBaseException):
    """Raised when authentication fails"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class AuthorizationError(FantasyAppBaseException):
    """Raised when authorization fails"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)