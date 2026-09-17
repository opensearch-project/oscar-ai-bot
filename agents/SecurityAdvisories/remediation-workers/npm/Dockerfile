# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# npm/yarn ecosystem CVE remediation worker (container image, runs as an ECS
# Fargate task). Build context = this directory
# (agents/SecurityAdvisories/remediation-workers/npm/).
FROM public.ecr.aws/lambda/python:3.12

# The python:3.12 base is Amazon Linux 2023 (glibc >= 2.28, dnf), which Node 22
# requires. Node is installed via nvm with multiple versions, mirroring the
# OpenSearch-Dashboards CI build image, so the toolchain tracks OSD instead of a
# single hardcoded pin. NODE_VERSION_LIST is installed; NODE_VERSION is the
# default on PATH (the current OSD .node-version). 22.22.0 is kept as the version
# the worker was tested with. yarn 1.22.x classic is installed per node version.
#
# gh CLI comes from GitHub's rpm repo (GPG-verified): the base image's microdnf
# lacks the config-manager plugin, so we write the repo file directly.
ENV NVM_DIR=/usr/local/nvm
ENV NODE_VERSION=22.23.0
ARG NODE_VERSION_LIST="22.22.0 22.23.0"

RUN dnf install -y git tar gzip findutils bash
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN mkdir -p "$NVM_DIR" && \
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash && \
    source "$NVM_DIR/nvm.sh" && \
    for v in $NODE_VERSION_LIST; do nvm install "$v" && nvm use "$v" && npm install -g yarn@1.22.22; done && \
    nvm alias default "$NODE_VERSION" && \
    printf '[gh-cli]\nname=packages for the GitHub CLI\nbaseurl=https://cli.github.com/packages/rpm\nenabled=1\ngpgcheck=1\ngpgkey=https://cli.github.com/packages/githubcli-archive-keyring.asc\n' > /etc/yum.repos.d/gh-cli.repo && \
    rpm --import https://cli.github.com/packages/githubcli-archive-keyring.asc && \
    dnf install -y gh && \
    dnf clean all && \
    source "$NVM_DIR/nvm.sh" && nvm use default && \
    node --version && yarn --version && gh --version
ENV PATH=$NVM_DIR/versions/node/v$NODE_VERSION/bin:$PATH

# main.py is the entrypoint: it reads the remediation payload from env vars and
# calls remediation.handle. We override the Lambda base image's runtime-client
# ENTRYPOINT to run it directly (the base image is used only for its AL2023 +
# Python + toolchain, not the Lambda runtime).
COPY remediation.py npm.py llm_planner.py main.py git-askpass.sh ${LAMBDA_TASK_ROOT}/
# git-askpass.sh feeds the token to git as the HTTPS password (via GIT_ASKPASS)
# so it never lands in a URL/argv/.git/config; ensure it's executable.
RUN chmod +x ${LAMBDA_TASK_ROOT}/git-askpass.sh

ENTRYPOINT ["/var/lang/bin/python"]
CMD ["/var/task/main.py"]
