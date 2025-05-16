"""Custom trace processor for debugging."""

import logging
from typing import Any
from agents.tracing import TracingProcessor, Trace, Span

logger = logging.getLogger(__name__)


class DebugTraceProcessor(TracingProcessor):
    """A simple trace processor that logs trace information."""
    
    def on_trace_start(self, trace: Trace) -> None:
        """Called when a trace starts."""
        logger.info(f"[TRACE START] {trace.name} (ID: {trace.trace_id})")
        if hasattr(trace, 'metadata') and trace.metadata:
            logger.info(f"[TRACE METADATA] {trace.metadata}")
    
    def on_trace_end(self, trace: Trace) -> None:
        """Called when a trace finishes."""
        logger.info(f"[TRACE END] {trace.name} (ID: {trace.trace_id})")
        if hasattr(trace, 'metadata') and trace.metadata:
            logger.info(f"[TRACE FINAL METADATA] {trace.metadata}")
        
        # Log spans within the trace
        if hasattr(trace, 'spans'):
            for span in trace.spans:
                span_name = getattr(span, 'name', span.__class__.__name__)
                logger.debug(f"  [SPAN] {span_name} (ID: {span.span_id})")
    
    def on_span_start(self, span: Span[Any]) -> None:
        """Called when a span starts."""
        # Get the span name from data attribute or class name
        span_name = span.__class__.__name__
        if hasattr(span, '_data') and hasattr(span._data, 'name'):
            span_name = span._data.name
        elif hasattr(span, 'data') and hasattr(span.data, 'name'):
            span_name = span.data.name
            
        logger.debug(f"[SPAN START] {span_name} (ID: {span.span_id})")
    
    def on_span_end(self, span: Span[Any]) -> None:
        """Called when a span finishes."""
        # Get the span name from data attribute or class name
        span_name = span.__class__.__name__
        if hasattr(span, '_data') and hasattr(span._data, 'name'):
            span_name = span._data.name
        elif hasattr(span, 'data') and hasattr(span.data, 'name'):
            span_name = span.data.name
            
        logger.debug(f"[SPAN END] {span_name} (ID: {span.span_id})")
    
    def shutdown(self) -> None:
        """Called when the application stops."""
        logger.debug("Shutting down debug trace processor")
    
    def force_flush(self) -> None:
        """Forces an immediate flush of all queued spans/traces."""
        logger.debug("Force flushing debug trace processor")