"""
Authentication and Authorization Module for A2A Protocol

This module provides authentication and authorization functionality for
Agent-to-Agent communication, including credential validation, security
level enforcement, and HTTP header authentication.
"""

import re
import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union
from ipaddress import ip_address, ip_network, AddressValueError

# Use official Google A2A types for AgentCard
from a2a.types import AgentCard
from models.jsonrpc import JSONRPCErrorCode
from enum import Enum

# Simple auth models for internal use (not part of A2A spec)
class CredentialType(str, Enum):
    """Types of authentication credentials"""
    BEARER_TOKEN = "bearer_token"
    API_KEY = "api_key"
    JWT_TOKEN = "jwt_token"

class SecurityLevel(str, Enum):
    """Security levels for access control"""
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    AUTHORIZED = "authorized"
    RESTRICTED = "restricted"

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when authentication fails"""
    def __init__(self, message: str, error_code: int = JSONRPCErrorCode.AUTHENTICATION_ERROR):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class AuthorizationError(Exception):
    """Raised when authorization fails"""
    def __init__(self, message: str, error_code: int = JSONRPCErrorCode.AUTHORIZATION_ERROR):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class AuthenticationResult:
    """Result of authentication validation"""
    def __init__(
        self,
        is_authenticated: bool,
        agent_id: Optional[str] = None,
        security_level: SecurityLevel = SecurityLevel.PUBLIC,
        scopes: Optional[List[str]] = None,
        credential_type: Optional[CredentialType] = None,
        error_message: Optional[str] = None
    ):
        self.is_authenticated = is_authenticated
        self.agent_id = agent_id
        self.security_level = security_level
        self.scopes = scopes or []
        self.credential_type = credential_type
        self.error_message = error_message


class AgentAuthenticator:
    """
    Handles authentication and authorization for A2A protocol agents
    """
    
    def __init__(self):
        self._agent_registry: Dict[str, AgentCard] = {}
        self._rate_limits: Dict[str, List[float]] = {}
    
    def register_agent(self, agent_card: AgentCard) -> None:
        """Register an agent and its credentials"""
        self._agent_registry[agent_card.agent_id] = agent_card
        logger.info(f"Registered agent {agent_card.agent_id} with security level {agent_card.security_level}")
    
    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent"""
        if agent_id in self._agent_registry:
            del self._agent_registry[agent_id]
            if agent_id in self._rate_limits:
                del self._rate_limits[agent_id]
            logger.info(f"Unregistered agent {agent_id}")
    
    def extract_credentials_from_headers(self, headers: Dict[str, str]) -> Optional[Tuple[CredentialType, str]]:
        """
        Extract authentication credentials from HTTP headers
        
        Args:
            headers: HTTP headers dictionary
            
        Returns:
            Tuple of (credential_type, credential_value) or None if no credentials found
        """
        # Check Authorization header for Bearer token
        auth_header = headers.get('Authorization', '').strip()
        if auth_header:
            if auth_header.startswith('Bearer '):
                token = auth_header[7:].strip()
                if token:
                    return (CredentialType.BEARER_TOKEN, token)
            elif auth_header.startswith('Token '):
                token = auth_header[6:].strip()
                if token:
                    return (CredentialType.API_KEY, token)
        
        # Check X-API-Key header
        api_key = headers.get('X-API-Key', '').strip()
        if api_key:
            return (CredentialType.API_KEY, api_key)
        
        # Check X-Auth-Token header
        auth_token = headers.get('X-Auth-Token', '').strip()
        if auth_token:
            return (CredentialType.JWT_TOKEN, auth_token)
        
        return None
    
    def validate_credential(
        self,
        credential_type: CredentialType,
        credential_value: str
    ) -> AuthenticationResult:
        """
        Validate a credential against registered agents
        
        Args:
            credential_type: Type of credential to validate
            credential_value: The credential value
            
        Returns:
            AuthenticationResult with validation details
        """
        for agent_id, agent_card in self._agent_registry.items():
            for credential in agent_card.credentials:
                if (credential.credential_type == credential_type and
                    credential.credential_value.get_secret_value() == credential_value):
                    
                    # Check if credential is expired
                    if credential.expires_at:
                        now = datetime.now(timezone.utc)
                        if now > credential.expires_at:
                            return AuthenticationResult(
                                is_authenticated=False,
                                error_message="Credential has expired"
                            )
                    
                    return AuthenticationResult(
                        is_authenticated=True,
                        agent_id=agent_id,
                        security_level=agent_card.security_level,
                        scopes=credential.scopes,
                        credential_type=credential_type
                    )
        
        return AuthenticationResult(
            is_authenticated=False,
            error_message="Invalid credentials"
        )
    
    def authenticate_request(
        self,
        headers: Dict[str, str],
        client_ip: Optional[str] = None
    ) -> AuthenticationResult:
        """
        Authenticate an incoming request based on headers
        
        Args:
            headers: HTTP headers from the request
            client_ip: Client IP address (optional)
            
        Returns:
            AuthenticationResult with authentication details
        """
        credentials = self.extract_credentials_from_headers(headers)
        if not credentials:
            return AuthenticationResult(
                is_authenticated=False,
                error_message="No authentication credentials provided"
            )
        
        credential_type, credential_value = credentials
        auth_result = self.validate_credential(credential_type, credential_value)
        
        if auth_result.is_authenticated and auth_result.agent_id:
            # Additional validation if IP whitelist is configured
            agent_card = self._agent_registry[auth_result.agent_id]
            if agent_card.default_security_policy and agent_card.default_security_policy.ip_whitelist:
                if not self._validate_ip_whitelist(client_ip, agent_card.default_security_policy.ip_whitelist):
                    return AuthenticationResult(
                        is_authenticated=False,
                        error_message="IP address not in whitelist"
                    )
            
            # Check rate limits
            if agent_card.default_security_policy and agent_card.default_security_policy.rate_limit:
                if not self._check_rate_limit(auth_result.agent_id, agent_card.default_security_policy.rate_limit):
                    return AuthenticationResult(
                        is_authenticated=False,
                        error_message="Rate limit exceeded"
                    )
        
        return auth_result
    
    def authorize_capability_access(
        self,
        auth_result: AuthenticationResult,
        capability_name: str,
        agent_card: AgentCard
    ) -> bool:
        """
        Check if an authenticated agent is authorized to access a capability
        
        Args:
            auth_result: Result from authentication
            capability_name: Name of the capability being accessed
            agent_card: Agent card of the capability provider
            
        Returns:
            True if authorized, False otherwise
            
        Raises:
            AuthorizationError: If authorization fails with details
        """
        if not auth_result.is_authenticated:
            raise AuthorizationError("Agent not authenticated")
        
        # Find the capability
        capability = None
        for cap in agent_card.capabilities:
            if cap.name == capability_name:
                capability = cap
                break
        
        if not capability:
            raise AuthorizationError(f"Capability '{capability_name}' not found")
        
        # Check capability-specific security policy
        security_policy = capability.security_policy or agent_card.default_security_policy
        if not security_policy:
            # No security policy means public access
            return True
        
        # Check security level requirement
        if not self._meets_security_level(auth_result.security_level, security_policy.required_security_level):
            raise AuthorizationError(
                f"Insufficient security level. Required: {security_policy.required_security_level}, "
                f"Provided: {auth_result.security_level}"
            )
        
        # Check credential type
        if (auth_result.credential_type and 
            security_policy.allowed_credential_types and
            auth_result.credential_type not in security_policy.allowed_credential_types):
            raise AuthorizationError(
                f"Credential type '{auth_result.credential_type.value}' not allowed for this capability"
            )
        
        # Check required scopes
        if security_policy.required_scopes:
            if not all(scope in auth_result.scopes for scope in security_policy.required_scopes):
                missing_scopes = set(security_policy.required_scopes) - set(auth_result.scopes)
                raise AuthorizationError(f"Missing required scopes: {missing_scopes}")
        
        # Check if policy is expired
        if security_policy.expires_at:
            now = datetime.now(timezone.utc)
            if now > security_policy.expires_at:
                raise AuthorizationError("Security policy has expired")
        
        return True
    
    def _validate_ip_whitelist(self, client_ip: Optional[str], whitelist: List[str]) -> bool:
        """Validate client IP against whitelist"""
        if not client_ip or not whitelist:
            return True
        
        try:
            client_addr = ip_address(client_ip)
            for allowed in whitelist:
                try:
                    if '/' in allowed:
                        # CIDR notation
                        if client_addr in ip_network(allowed, strict=False):
                            return True
                    else:
                        # Single IP
                        if client_addr == ip_address(allowed):
                            return True
                except AddressValueError:
                    logger.warning(f"Invalid IP/network in whitelist: {allowed}")
                    continue
            return False
        except AddressValueError:
            logger.warning(f"Invalid client IP address: {client_ip}")
            return False
    
    def _check_rate_limit(self, agent_id: str, rate_limit: int) -> bool:
        """Check if agent is within rate limit"""
        now = time.time()
        hour_ago = now - 3600  # 1 hour ago
        
        # Initialize or clean old entries
        if agent_id not in self._rate_limits:
            self._rate_limits[agent_id] = []
        
        # Remove requests older than 1 hour
        self._rate_limits[agent_id] = [
            timestamp for timestamp in self._rate_limits[agent_id]
            if timestamp > hour_ago
        ]
        
        # Check if within limit
        if len(self._rate_limits[agent_id]) >= rate_limit:
            return False
        
        # Add current request
        self._rate_limits[agent_id].append(now)
        return True
    
    def _meets_security_level(self, provided: SecurityLevel, required: SecurityLevel) -> bool:
        """Check if provided security level meets requirement"""
        level_hierarchy = {
            SecurityLevel.PUBLIC: 0,
            SecurityLevel.AUTHENTICATED: 1,
            SecurityLevel.AUTHORIZED: 2,
            SecurityLevel.RESTRICTED: 3
        }
        
        return level_hierarchy.get(provided, 0) >= level_hierarchy.get(required, 0)


# Global authenticator instance
authenticator = AgentAuthenticator()