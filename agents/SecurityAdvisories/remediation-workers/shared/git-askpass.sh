#!/bin/sh
# GIT_ASKPASS helper: echoes the GitHub token as the HTTPS password so the token
# never appears in the clone/push URL, the command line/argv, or .git/config.
# The username (x-access-token) is supplied in the URL, so git only asks for the
# password; the token is read from the environment (GH_TOKEN), set per-run.
echo "$GH_TOKEN"
