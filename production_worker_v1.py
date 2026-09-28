# -*- coding: utf-8 -*-
"""Compatibility entrypoint. Render keeps its existing start command while production uses shared-WS v2."""
from production_worker_v2_shared_ws import main

if __name__=="__main__":
    main()
