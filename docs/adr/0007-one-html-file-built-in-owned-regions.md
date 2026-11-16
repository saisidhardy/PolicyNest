---
status: proposed (AI-answered — needs human confirmation; GRILL_LOG G-20, G-21)
---
# One HTML file, built in parallel through owned regions

The app stays one self-contained `PolicyNest.html`, with no build tools beyond the wrapper script. That is the user's architecture decision, the claude.ai artifact copy needs one file, and the engine block must stay extractable (ADR 0001). To let several agents build at once:

- the file is divided once into named regions with start and end markers;
- each work lane owns specific regions;
- only one lane writes the file at a time, in its own git worktree;
- a single integrator merges the lanes in a fixed order and runs the checks after each merge.

Work outside the HTML file runs fully in parallel. We considered splitting the source into several files joined at build time. It is the fallback if region merges conflict often, and it needs the user's consent because it changes the architecture.

## Consequences

- The project folder becomes a git repository, with `.env`, the specimen originals and caches ignored.
- No lane may edit the engine block unless its brief says so; any such edit re-runs the evaluation.
