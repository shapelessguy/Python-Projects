"""CyanManager's services: one folder each, run as threads by main_logic.py.

    services/<name>/
        service.py          NAME (a plain string), PARAMETERS and entrypoint(thread_manager)
        requirements.txt    what only this service needs (optional)
        tools/              executables only this service runs (optional)

Shared code stays at the top level (utils, functions/, gui/, api_auth). The
launcher installs only the top-level requirements.txt (ensure_deps.py); a
service's own is installed from its "Install dependencies" button in the
General tab, and until then the service is not imported (service_deps.py).
"""
