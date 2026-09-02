# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# npm/yarn ecosystem CVE remediation worker (container image, runs as an ECS
# Fargate task). Build context = this directory
# (agents/SecurityAdvisories/remediation-workers/npm/).
FROM public.ecr.aws/lambda/python:3.12

# The python:3.12 base is Amazon Linux 2023 (glibc >= 2.28, dnf), which Node 22
# requires. Toolchain matches what OpenSearch-Dashboards builds with on main:
# Node 22 (OSD pins 22.22.0) and yarn 1.22.x classic. Dynamic per-repo toolchain
# detection is a deferred follow-up.
#
# Node is installed from the official pinned tarball and verified against a
# committed SHA256 — no `curl | bash`, so the build fails unless the download
# matches the reviewed hash. To bump Node, update BOTH values below from
# https://nodejs.org/dist/v<version>/SHASUMS256.txt (linux-arm64 .tar.gz — the
# task runs on arm64/Graviton). yarn is a pinned global install using the npm
# that ships inside that verified Node tarball.
#
# gh CLI comes from GitHub's rpm repo (GPG-verified): the base image's microdnf
# lacks the config-manager plugin, so we write the repo file directly.
ARG NODE_VERSION=22.22.0
ARG NODE_SHA256=25ba95dfb96871fa2ef977f11f95ea90818c8fa15c0f2110771db08d4ba423be
RUN dnf install -y git tar gzip findutils && \
    curl -fsSLo /tmp/node.tar.gz "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-arm64.tar.gz" && \
    echo "${NODE_SHA256}  /tmp/node.tar.gz" | sha256sum -c - && \
    tar -xzf /tmp/node.tar.gz -C /usr/local --strip-components=1 && \
    rm /tmp/node.tar.gz && \
    npm install -g yarn@1.22.22 && \
    printf '[gh-cli]\nname=packages for the GitHub CLI\nbaseurl=https://cli.github.com/packages/rpm\nenabled=1\ngpgcheck=1\ngpgkey=https://cli.github.com/packages/githubcli-archive-keyring.asc\n' > /etc/yum.repos.d/gh-cli.repo && \
    dnf install -y gh && \
    dnf clean all && \
    node --version && yarn --version && gh --version

# main.py is the entrypoint: it reads the remediation payload from env vars and
# calls remediation.handle. We override the Lambda base image's runtime-client
# ENTRYPOINT to run it directly (the base image is used only for its AL2023 +
# Python + toolchain, not the Lambda runtime).
COPY remediation.py npm.py main.py git-askpass.sh ${LAMBDA_TASK_ROOT}/
# git-askpass.sh feeds the token to git as the HTTPS password (via GIT_ASKPASS)
# so it never lands in a URL/argv/.git/config; ensure it's executable.
RUN chmod +x ${LAMBDA_TASK_ROOT}/git-askpass.sh

ENTRYPOINT ["/var/lang/bin/python"]
CMD ["/var/task/main.py"]
