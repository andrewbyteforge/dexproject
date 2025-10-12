"""
Analytics Middleware Module

Automatically tracks HTTP request metrics for monitoring.
This middleware records request duration, status codes, and endpoints
without requiring any manual instrumentation.

File: dexproject/analytics/middleware.py
"""

import logging
import time
from typing import Callable, Optional
from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin
from django.urls import resolve, Resolver404

from .metrics import metrics_recorder

logger = logging.getLogger(__name__)


class MetricsMiddleware(MiddlewareMixin):
    """
    Middleware to automatically track HTTP request metrics.
    
    Records:
    - Request count by method, endpoint, and status
    - Request duration histogram
    - In-progress request gauge
    
    This middleware should be added near the end of MIDDLEWARE in settings.py
    to capture the full request lifecycle.
    """
    
    def __init__(self, get_response: Callable):
        """
        Initialize middleware.
        
        Args:
            get_response: Next middleware or view in the chain
        """
        self.get_response = get_response
        super().__init__(get_response)
        logger.info("MetricsMiddleware initialized")
    
    def process_request(self, request: HttpRequest) -> None:
        """
        Process request before view is called.
        
        Records start time and increments in-progress counter.
        
        Args:
            request: Django HTTP request object
        """
        # Record start time
        request._metrics_start_time = time.time()
        
        # Increment in-progress requests
        metrics_recorder.increment_requests_in_progress()
    
    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse
    ) -> HttpResponse:
        """
        Process response after view has been called.
        
        Records request metrics and decrements in-progress counter.
        
        Args:
            request: Django HTTP request object
            response: Django HTTP response object
            
        Returns:
            The response object (unchanged)
        """
        try:
            # Calculate request duration
            if hasattr(request, '_metrics_start_time'):
                duration = time.time() - request._metrics_start_time
                
                # Get endpoint name
                endpoint = self._get_endpoint_name(request)
                
                # Get HTTP method
                method = request.method
                
                # Get status code
                status_code = response.status_code
                
                # Record metrics
                metrics_recorder.record_http_request(
                    method=method,
                    endpoint=endpoint,
                    status_code=status_code,
                    duration_seconds=duration
                )
                
                # Log slow requests (> 1 second)
                if duration > 1.0:
                    logger.warning(
                        f"Slow request: {method} {endpoint} took {duration:.3f}s"
                    )
            
            # Decrement in-progress requests
            metrics_recorder.decrement_requests_in_progress()
            
        except Exception as e:
            logger.error(f"Error in MetricsMiddleware.process_response: {e}")
            # Still decrement counter even on error
            metrics_recorder.decrement_requests_in_progress()
        
        return response
    
    def process_exception(
        self,
        request: HttpRequest,
        exception: Exception
    ) -> None:
        """
        Process exceptions that occur during request handling.
        
        Records error metrics and decrements in-progress counter.
        
        Args:
            request: Django HTTP request object
            exception: Exception that was raised
        """
        try:
            # Calculate request duration
            if hasattr(request, '_metrics_start_time'):
                duration = time.time() - request._metrics_start_time
                
                # Get endpoint name
                endpoint = self._get_endpoint_name(request)
                
                # Get HTTP method
                method = request.method
                
                # Record as 500 error
                metrics_recorder.record_http_request(
                    method=method,
                    endpoint=endpoint,
                    status_code=500,
                    duration_seconds=duration
                )
                
                logger.error(
                    f"Request exception: {method} {endpoint} - {exception}"
                )
            
            # Decrement in-progress requests
            metrics_recorder.decrement_requests_in_progress()
            
        except Exception as e:
            logger.error(f"Error in MetricsMiddleware.process_exception: {e}")
            # Still decrement counter
            metrics_recorder.decrement_requests_in_progress()
    
    def _get_endpoint_name(self, request: HttpRequest) -> str:
        """
        Get a clean endpoint name for the request.
        
        Converts URL patterns to generic endpoint names to avoid
        high cardinality in metrics (e.g., /user/123 -> /user/:id).
        
        Args:
            request: Django HTTP request object
            
        Returns:
            Endpoint name string
        """
        try:
            # Try to resolve URL to view name
            resolved = resolve(request.path_info)
            
            # Use view name if available
            if resolved.url_name:
                # Construct endpoint from app and view name
                if resolved.namespace:
                    endpoint = f"{resolved.namespace}:{resolved.url_name}"
                else:
                    endpoint = resolved.url_name
            else:
                # Fall back to view function name
                view_name = resolved.func.__name__
                endpoint = view_name
            
            return endpoint
            
        except Resolver404:
            # URL not found - use path with parameters stripped
            return self._strip_parameters(request.path_info)
        except Exception as e:
            logger.debug(f"Error resolving endpoint name: {e}")
            return self._strip_parameters(request.path_info)
    
    def _strip_parameters(self, path: str) -> str:
        """
        Strip numeric and UUID parameters from path.
        
        Converts paths like /api/trade/123 to /api/trade/:id
        to reduce cardinality in metrics.
        
        Args:
            path: URL path
            
        Returns:
            Path with parameters replaced
        """
        import re
        
        # Replace UUIDs with :uuid
        path = re.sub(
            r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '/:uuid',
            path,
            flags=re.IGNORECASE
        )
        
        # Replace numeric IDs with :id
        path = re.sub(r'/\d+', '/:id', path)
        
        # Replace hex strings (tx hashes) with :hash
        path = re.sub(r'/0x[0-9a-f]+', '/:hash', path, flags=re.IGNORECASE)
        
        return path


class DatabaseMetricsMiddleware(MiddlewareMixin):
    """
    Middleware to track database query metrics.
    
    This middleware uses Django's database query logging to track
    query count and duration per request.
    
    Note: Only works when DEBUG=True or when using Django Debug Toolbar.
    For production, use database-level monitoring instead.
    """
    
    def __init__(self, get_response: Callable):
        """Initialize middleware."""
        self.get_response = get_response
        super().__init__(get_response)
        logger.info("DatabaseMetricsMiddleware initialized")
    
    def process_request(self, request: HttpRequest) -> None:
        """Record initial query count."""
        from django.db import connection
        request._queries_before = len(connection.queries)
    
    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse
    ) -> HttpResponse:
        """Record database query metrics."""
        try:
            from django.db import connection
            from django.conf import settings
            
            if settings.DEBUG and hasattr(request, '_queries_before'):
                queries_count = len(connection.queries) - request._queries_before
                
                # Log if excessive queries
                if queries_count > 50:
                    logger.warning(
                        f"High query count: {queries_count} queries for "
                        f"{request.method} {request.path}"
                    )
                
                # Record query metrics
                for query in connection.queries[request._queries_before:]:
                    # Parse query type (SELECT, INSERT, UPDATE, DELETE)
                    operation = self._get_query_operation(query['sql'])
                    duration = float(query['time'])
                    
                    metrics_recorder.record_db_query(
                        operation=operation,
                        duration_seconds=duration
                    )
            
            # Update connection count
            if hasattr(connection, 'queries'):
                active_connections = len(connection.queries)
                metrics_recorder.update_db_connections(active_connections)
                
        except Exception as e:
            logger.error(f"Error in DatabaseMetricsMiddleware: {e}")
        
        return response
    
    def _get_query_operation(self, sql: str) -> str:
        """
        Extract operation type from SQL query.
        
        Args:
            sql: SQL query string
            
        Returns:
            Operation type ('select', 'insert', 'update', 'delete', 'other')
        """
        sql_upper = sql.strip().upper()
        
        if sql_upper.startswith('SELECT'):
            return 'select'
        elif sql_upper.startswith('INSERT'):
            return 'insert'
        elif sql_upper.startswith('UPDATE'):
            return 'update'
        elif sql_upper.startswith('DELETE'):
            return 'delete'
        else:
            return 'other'


class CacheMetricsWrapper:
    """
    Wrapper for Django cache to track metrics.
    
    This is not a middleware but a cache backend wrapper.
    Usage instructions will be provided in settings.py update.
    """
    
    def __init__(self, cache_backend):
        """
        Initialize cache wrapper.
        
        Args:
            cache_backend: Original cache backend instance
        """
        self._cache = cache_backend
        self.logger = logging.getLogger('analytics.cache')
    
    def get(self, key, default=None, version=None):
        """Wrap cache get operation."""
        start_time = time.time()
        try:
            result = self._cache.get(key, default, version)
            duration = time.time() - start_time
            
            # Record hit or miss
            status = 'hit' if result is not None else 'miss'
            metrics_recorder.record_cache_operation(
                operation='get',
                status=status,
                duration_seconds=duration
            )
            
            return result
        except Exception as e:
            duration = time.time() - start_time
            metrics_recorder.record_cache_operation(
                operation='get',
                status='error',
                duration_seconds=duration
            )
            self.logger.error(f"Cache get error: {e}")
            raise
    
    def set(self, key, value, timeout=None, version=None):
        """Wrap cache set operation."""
        start_time = time.time()
        try:
            result = self._cache.set(key, value, timeout, version)
            duration = time.time() - start_time
            
            metrics_recorder.record_cache_operation(
                operation='set',
                status='success',
                duration_seconds=duration
            )
            
            return result
        except Exception as e:
            duration = time.time() - start_time
            metrics_recorder.record_cache_operation(
                operation='set',
                status='error',
                duration_seconds=duration
            )
            self.logger.error(f"Cache set error: {e}")
            raise
    
    def delete(self, key, version=None):
        """Wrap cache delete operation."""
        start_time = time.time()
        try:
            result = self._cache.delete(key, version)
            duration = time.time() - start_time
            
            metrics_recorder.record_cache_operation(
                operation='delete',
                status='success',
                duration_seconds=duration
            )
            
            return result
        except Exception as e:
            duration = time.time() - start_time
            metrics_recorder.record_cache_operation(
                operation='delete',
                status='error',
                duration_seconds=duration
            )
            self.logger.error(f"Cache delete error: {e}")
            raise
    
    def __getattr__(self, name):
        """Forward all other methods to the wrapped cache."""
        return getattr(self._cache, name)


# Log module initialization
logger.info("Analytics middleware module loaded")