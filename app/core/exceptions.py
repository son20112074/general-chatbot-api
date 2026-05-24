


class ProxyServiceException(Exception):
    """Base exception for the Proxy Service."""

class InvalidProxyRequestException(ProxyServiceException):
    """Exception raised for invalid proxy requests."""

class ProxyRequestTimeoutException(ProxyServiceException):
    """Exception raised when a proxy request times out."""

class UnsupportedProtocolException(ProxyServiceException):
    """Exception raised for unsupported protocols."""

class AuthenticationException(ProxyServiceException):
    """Exception raised for authentication failures."""
    
class ConnectionErrorException(BaseException):
    """Exception raised when a connection error occurs."""
    pass
