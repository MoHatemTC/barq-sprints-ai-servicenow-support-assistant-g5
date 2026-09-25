"""
Incident handler.

This module provides the default handler used to process
an incident after the Celery worker finishes validation
and security checks.
"""

from Services.run_pipeline import process_incident


def handle_incident(incident_context):
    """
    Process the incident using the application's AI pipeline.

    The handler acts as a small abstraction layer between
    the Celery worker and the actual incident-processing logic.
    """

    return process_incident(incident_context)

