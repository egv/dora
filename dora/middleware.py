"""
Middleware components for A2A Protocol authentication and authorization

This module provides FastAPI middleware for handling authentication,
authorization, and security enforcement for A2A protocol requests.
"""

import logging
from typing import Callable, Dict, Optional
from fastapi import Request, Response, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware

from dora.auth import authenticator, AuthenticationResult, AuthenticationError, AuthorizationError
from models.jsonrpc import JSONRPCErrorCode

logger = logging.getLogger(__name__)


class A2AAuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Middleware for A2A protocol authentication and authorization
    """
    
    def __init__(self, app, exclude_paths: Optional[list] = None):
        """
        Initialize authentication middleware
        
        Args:
            app: FastAPI application instance
            exclude_paths: List of paths to exclude from authentication
        """
        super().__init__(app)
        self.exclude_paths = exclude_paths or [
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc"
        ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request through authentication middleware
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain
            
        Returns:
            HTTP response
        """
        # Skip authentication for excluded paths
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)
        
        # Extract client IP
        client_ip = self._get_client_ip(request)
        
        # Convert headers to dict
        headers = dict(request.headers)
        
        try:
            # Authenticate the request
            auth_result = authenticator.authenticate_request(headers, client_ip)
            
            # Store authentication result in request state for later use
            request.state.auth_result = auth_result
            request.state.client_ip = client_ip
            
            if not auth_result.is_authenticated:
                logger.warning(
                    f"Authentication failed for {client_ip}: {auth_result.error_message}"
                )
                raise HTTPException(
                    status_code=401,
                    detail={
                        "error": "Authentication failed",
                        "message": auth_result.error_message,
                        "error_code": JSONRPCErrorCode.AUTHENTICATION_ERROR
                    }
                )
            
            logger.info(
                f"Authentication successful for agent {auth_result.agent_id} "
                f"from {client_ip} with security level {auth_result.security_level}"
            )
            
            # Continue to next middleware/handler
            response = await call_next(request)
            
            # Add authentication info to response headers (optional)
            if auth_result.agent_id:
                response.headers["X-Authenticated-Agent"] = auth_result.agent_id
                response.headers["X-Security-Level"] = auth_result.security_level.value
            
            return response
            
        except AuthenticationError as e:
            logger.error(f"Authentication error for {client_ip}: {e.message}")
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "Authentication error",
                    "message": e.message,
                    "error_code": e.error_code
                }
            )
        except AuthorizationError as e:
            logger.error(f"Authorization error for {client_ip}: {e.message}")
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Authorization error",
                    "message": e.message,
                    "error_code": e.error_code
                }
            )
        except Exception as e:
            logger.exception(f"Unexpected error in authentication middleware for {client_ip}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Internal server error",
                    "message": "Authentication service unavailable",
                    "error_code": JSONRPCErrorCode.INTERNAL_ERROR
                }
            )
    
    def _get_client_ip(self, request: Request) -> Optional[str]:
        """Extract client IP address from request"""
        # Check X-Forwarded-For header (proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        # Check X-Real-IP header (nginx)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        # Use client host from request
        if request.client:
            return request.client.host
        
        return None


class A2AAuthorizationDependency:
    """
    FastAPI dependency for capability-specific authorization
    """
    
    def __init__(self, capability_name: str, required_scopes: Optional[list] = None):
        """
        Initialize authorization dependency
        
        Args:
            capability_name: Name of capability being accessed
            required_scopes: Additional required scopes
        """
        self.capability_name = capability_name
        self.required_scopes = required_scopes or []
    
    async def __call__(self, request: Request) -> AuthenticationResult:
        """
        Validate authorization for capability access
        
        Args:
            request: HTTP request with auth_result in state
            
        Returns:
            AuthenticationResult if authorized
            
        Raises:
            HTTPException: If authorization fails
        """
        # Get authentication result from middleware
        auth_result: AuthenticationResult = getattr(request.state, 'auth_result', None)
        if not auth_result:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "Authentication required",
                    "message": "Request not authenticated",
                    "error_code": JSONRPCErrorCode.AUTHENTICATION_ERROR
                }
            )
        
        if not auth_result.is_authenticated:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "Authentication failed",
                    "message": auth_result.error_message,
                    "error_code": JSONRPCErrorCode.AUTHENTICATION_ERROR
                }
            )
        
        # Check additional scopes if required
        if self.required_scopes:
            missing_scopes = set(self.required_scopes) - set(auth_result.scopes)
            if missing_scopes:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "Insufficient scopes",
                        "message": f"Missing required scopes: {missing_scopes}",
                        "error_code": JSONRPCErrorCode.AUTHORIZATION_ERROR
                    }
                )
        
        logger.info(
            f"Authorization successful for agent {auth_result.agent_id} "
            f"accessing capability {self.capability_name}"
        )
        
        return auth_result


class A2ABearerAuth(HTTPBearer):
    """
    FastAPI security scheme for A2A Bearer token authentication
    """
    
    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)
    
    async def __call__(self, request: Request) -> Optional[HTTPAuthorizationCredentials]:
        """
        Extract and validate Bearer token from request
        
        Args:
            request: HTTP request
            
        Returns:
            HTTP authorization credentials if valid
        """
        credentials = await super().__call__(request)
        if credentials:
            # Additional validation can be added here
            return credentials
        return None


def get_authenticated_agent(request: Request) -> AuthenticationResult:
    """
    Dependency function to get authenticated agent from request
    
    Args:
        request: HTTP request with auth_result in state
        
    Returns:
        AuthenticationResult for the authenticated agent
        
    Raises:
        HTTPException: If not authenticated
    """
    auth_result: AuthenticationResult = getattr(request.state, 'auth_result', None)
    if not auth_result or not auth_result.is_authenticated:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Authentication required",
                "message": "Request not authenticated",
                "error_code": JSONRPCErrorCode.AUTHENTICATION_ERROR
            }
        )
    return auth_result


def require_security_level(min_level: str):
    """
    Dependency factory for requiring minimum security level
    
    Args:
        min_level: Minimum required security level (public, authenticated, authorized, restricted)
        
    Returns:
        Dependency function that validates security level
    """
    from models.a2a import SecurityLevel
    
    # Convert string to SecurityLevel enum
    required_level = SecurityLevel(min_level.lower())
    
    def security_level_dependency(request: Request) -> AuthenticationResult:
        auth_result = get_authenticated_agent(request)
        
        # Check security level hierarchy
        level_hierarchy = {
            SecurityLevel.PUBLIC: 0,
            SecurityLevel.AUTHENTICATED: 1,
            SecurityLevel.AUTHORIZED: 2,
            SecurityLevel.RESTRICTED: 3
        }
        
        provided_level_value = level_hierarchy.get(auth_result.security_level, 0)
        required_level_value = level_hierarchy.get(required_level, 0)
        
        if provided_level_value < required_level_value:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Insufficient security level",
                    "message": f"Required: {required_level.value}, Provided: {auth_result.security_level.value}",
                    "error_code": JSONRPCErrorCode.AUTHORIZATION_ERROR
                }
            )
        
        return auth_result
    
    return security_level_dependency


def require_scopes(scopes: list):
    """
    Dependency factory for requiring specific scopes
    
    Args:
        scopes: List of required scopes
        
    Returns:
        Dependency function that validates scopes
    """
    def scopes_dependency(request: Request) -> AuthenticationResult:
        auth_result = get_authenticated_agent(request)
        
        missing_scopes = set(scopes) - set(auth_result.scopes)
        if missing_scopes:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Insufficient scopes",
                    "message": f"Missing required scopes: {missing_scopes}",
                    "error_code": JSONRPCErrorCode.AUTHORIZATION_ERROR
                }
            )
        
        return auth_result
    
    return scopes_dependency