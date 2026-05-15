class AppError(Exception):
    """Base application error."""


class ValidationError(AppError):
    """Raised when input data is invalid."""


class NotFoundError(AppError):
    """Raised when a record cannot be found."""


class ConflictError(AppError):
    """Raised when a record already exists."""


class PermissionDenied(AppError):
    """Raised when a role is not allowed to perform an action."""


class ComplianceGateError(AppError):
    """Raised when a compliance gate blocks an operation."""
