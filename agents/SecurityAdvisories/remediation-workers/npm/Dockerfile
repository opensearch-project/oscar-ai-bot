# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# npm/yarn ecosystem CVE remediation worker (container image, runs as an ECS
# Fargate task). Build context = this directory
# (agents/SecurityAdvisories/remediation-workers/npm/).
FROM public.ecr.aws/lambda/python:3.12

# The python:3.12 base is Amazon Linux 2023 (glibc >= 2.28, dnf), which Node 22
# requires. Toolchain is pinned to what OpenSearch-Dashboards CI reads on main:
# Node 22 (from OSD .nvmrc) and yarn 1.22.x classic (engines.yarn ^1.22.10).
# Dynamic per-repo toolchain detection is a deferred follow-up.
#
# gh CLI comes from GitHub's rpm repo: the base image's microdnf lacks the
# config-manager plugin, so we write the repo file directly.
RUN dnf install -y git tar findutils && \
    curl -fsSL https://rpm.nodesource.com/setup_22.x | bash - && \
    dnf install -y nodejs && \
    npm install -g yarn@1.22.22 && \
    printf '[gh-cli]\nname=packages for the GitHub CLI\nbaseurl=https://cli.github.com/packages/rpm\nenabled=1\ngpgcheck=1\ngpgkey=https://cli.github.com/packages/githubcli-archive-keyring.asc\n' > /etc/yum.repos.d/gh-cli.repo && \
    dnf install -y gh && \
    dnf clean all && \
    node --version && yarn --version && gh --version

# main.py is the entrypoint: it reads the remediation payload from env vars and
# calls remediation.handle. We override the Lambda base image's runtime-client
# ENTRYPOINT to run it directly (the base image is used only for its AL2023 +
# Python + toolchain, not the Lambda runtime).
COPY remediation.py npm.py main.py ${LAMBDA_TASK_ROOT}/

ENTRYPOINT ["/var/lang/bin/python"]
CMD ["/var/task/main.py"]
