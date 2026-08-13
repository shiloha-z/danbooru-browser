# Stateful execution model

The node is deliberately not deterministic: in auto and list modes the cursor advances one post per node invocation, and in manual mode the output is whatever the panel currently selects. The browse session (search conditions, loaded pages, cursor, list, selection) lives in the frontend and is serialized into the workflow JSON, so a saved workflow reopens at the same spot and re-fetches its results. This trades graph determinism for interactive browsing — a queue run outputs whichever post the cursor is on at that moment.
