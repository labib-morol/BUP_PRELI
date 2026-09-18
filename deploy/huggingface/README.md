# Hugging Face Spaces fallback deployment

Free, no credit card, and the free tier only sleeps after 48 hours of **zero**
traffic - so it needs no keep-alive ping, unlike Render free. Use this if the
Render deployment misbehaves.

Two ways to create the Space:

## A. From the published image (keeps the source private)

1. Create a Docker Space at https://huggingface.co/new-space
2. Push only these two files to the Space repository:

   - this directory's `Dockerfile` (a single `FROM` line referring to the image
     published on Docker Hub)
   - `space-README.md`, renamed to `README.md` in the Space repository

3. In the Space's **Settings -> Variables and secrets**, add `GEMINI_API_KEY`
   as a *secret* (never as a plain variable).

The Space repository then contains no application source at all - only a base-image
reference - which keeps the GitHub repository and the code private while the
endpoint itself stays public.

## B. From source (simpler, but the Space repo is public)

1. Create a Docker Space.
2. Add the `sdk: docker` front-matter from `space-README.md` to the top of this
   repository's `README.md`.
3. Push this repository to the Space remote.

Requires `app_port: 8000` in the front-matter, which both variants already set.
