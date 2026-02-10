from google.api_core import exceptions as google_exceptions
from google.auth import exceptions as auth_exceptions
from fastapi import HTTPException
import logging

logger = logging.getLogger("ErrorHandler")

def classify_error(e: Exception, service_name: str = "Service") -> dict:
    """
    [Error Classifier]
    Decides whether to show raw error (transient) or 'Contact Admin' (config error).
    Returns a dictionary suitable for JSON response.
    """
    error_msg = str(e)
    error_code = "UNKNOWN"
    action = "check_logs" # default action (internal error)
    
    # 1. Google Auth Errors
    if isinstance(e, auth_exceptions.DefaultCredentialsError) or "could not automatically determine credentials" in str(e).lower():
        error_code = "AUTH_MISSING"
        error_msg = "Server Credential Missing. Contact Admin."
        action = "contact_admin"

    # 2. IAM Permission Errors
    elif isinstance(e, google_exceptions.PermissionDenied) or "403" in str(e):
        error_code = "PERM_DENIED"
        error_msg = f"IAM Permission Denied for {service_name}. Contact Admin."
        action = "contact_admin"

    # 3. Connection/Availability Errors
    elif isinstance(e, google_exceptions.ServiceUnavailable) or "503" in str(e):
        error_code = "SERVICE_DOWN"
        error_msg = f"{service_name} is temporarily unavailable. Try again."
        action = "retry"
    elif "deadline" in str(e).lower() or "timeout" in str(e).lower():
        error_code = "TIMEOUT"
        error_msg = f"{service_name} connection confirmed, but too slow."
        action = "retry"
        
    # 4. HTTP Exceptions (Pass through friendly message if available)
    elif isinstance(e, HTTPException):
        # Already handled, just extract detail
        return {
            "status": "error",
            "code": "HTTP_ERR",
            "message": e.detail,
            "action": "show_message", # Just show what backend said
            "raw_error": str(e)
        }

    
    # 5. Generic Internal Error
    else:
        error_code = "INTERNAL_ERROR"
        # [Security Fix] Mask internal errors for end-users
        error_msg = "An unexpected system error occurred. Please contact the administrator."
        # In production, we might mask this. For now, detailed is better for debugging.
        action = "contact_admin"

    return {
        "status": "error",
        "code": error_code,
        "message": error_msg,
        "action": action,
        "raw_error": str(e) # Internal logs can still see this
    }

def raise_classified_http_exception(e: Exception, service_name: str = "Service", user_id: str = "unknown"):
    """
    Classifies the error, LOGS it to system logs, and raises a FastAPI HTTPException.
    [Auto-Logging] Now connects to log_service.log_system_error
    """
    # [Safe Integration] Try-Except for missing log_service dependency
    log_func = None
    try:
        from app.services.log_service import log_system_error
        log_func = log_system_error
    except ImportError:
        # Fallback if log_service.py hasn't been updated yet
        logger.warning("[ErrorHandler] log_system_error not found in log_service. using fallback.")
    
    import traceback
    
    error_info = classify_error(e, service_name)
    
    # [Start] Centralized Logging
    # Extract Traceback for debugging
    tb_str = "".join(traceback.format_tb(e.__traceback__)) if e.__traceback__ else str(e)
    
    if log_func:
        log_func(
            error_code=error_info['code'],
            message=error_info['message'],
            path=service_name, 
            user_id=user_id,
            stack_trace=tb_str
        )
    else:
        # Fallback Logging
        logger.error(f"❌ [{service_name}] Error: {error_info['code']} - {error_info['message']}")
        logger.error(f"Traceback: {tb_str}")
        
    # [End] Centralized Logging
    
    # Map internal error codes to HTTP Status Codes
    status_code = 500
    if error_info['code'] == "AUTH_MISSING":
        status_code = 500 # Server Misconfiguration
    elif error_info['code'] == "PERM_DENIED":
        status_code = 403 # Forbidden
    elif error_info['code'] in ["SERVICE_DOWN", "TIMEOUT"]:
        status_code = 503 # Service Unavailable
        
    raise HTTPException(status_code=status_code, detail=error_info)
