"""Process-local coordination for queue archive and safe Render restart."""
import threading
archive_restart_lock = threading.Lock()
