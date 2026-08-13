# Frontend panel backed by server routes

The browse UI is a custom node frontend that reaches the site APIs through routes we register on ComfyUI's prompt server, instead of driving data through node execution. Site APIs reject browser-side cross-origin requests, and node execution is too slow and awkward a channel for interactive browsing; the Python node itself stays a thin executor that reads the current panel state at queue time.
