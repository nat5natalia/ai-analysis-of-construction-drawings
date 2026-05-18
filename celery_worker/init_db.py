"""Deprecated vector index initializer.

Vector indexing has moved out of celery_worker. The worker should only
orchestrate background tasks and call drawing_agent for analysis/indexing.
"""

if __name__ == "__main__":
    print("Vector indexing is handled by drawing_agent; celery_worker/init_db.py is deprecated.")
