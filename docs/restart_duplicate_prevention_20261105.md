# Restart duplicate prevention

A restart request must never be repeated blindly. Persist a per-day attempt record on durable storage before requesting restart. A successful API response is not proof of healthy recovery. An ambiguous response must be treated as attempted, and a separate health check and LINE notification are required. The existing preflight leaves restart_attempted unknown until a trustworthy durable record is wired in. No production automation is enabled by this document.
