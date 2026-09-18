# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# maven/Gradle ecosystem CVE remediation worker (container image, runs as an ECS
# Fargate task). Build context = the parent remediation-workers/ directory
# (so this can COPY the shared/ flow alongside the maven/ strategy).
FROM public.ecr.aws/lambda/python:3.12

# The maven plugin fix is a pure text edit of build.gradle (no lockfile, no jar
# checksums, no Gradle build), so this image needs only git + Python + gh — no
# Node/yarn (unlike npm) and no JDK/Gradle. Much lighter than the npm image.
#
# gh CLI comes from GitHub's rpm repo (GPG-verified): the base image's microdnf
# lacks the config-manager plugin, so we write the repo file directly.
RUN dnf install -y git && \
    printf '[gh-cli]\nname=packages for the GitHub CLI\nbaseurl=https://cli.github.com/packages/rpm\nenabled=1\ngpgcheck=1\ngpgkey=https://cli.github.com/packages/githubcli-archive-keyring.asc\n' > /etc/yum.repos.d/gh-cli.repo && \
    rpm --import https://cli.github.com/packages/githubcli-archive-keyring.asc && \
    dnf install -y gh && \
    dnf clean all && \
    git --version && gh --version

# main.py is the entrypoint: it reads the remediation payload from env vars and
# calls remediation.handle. We override the Lambda base image's runtime-client
# ENTRYPOINT to run it directly (the base image is used only for its AL2023 +
# Python, not the Lambda runtime).
COPY shared/remediation.py shared/git-askpass.sh maven/maven.py maven/main.py ${LAMBDA_TASK_ROOT}/
# git-askpass.sh feeds the token to git as the HTTPS password (via GIT_ASKPASS)
# so it never lands in a URL/argv/.git/config; ensure it's executable.
RUN chmod +x ${LAMBDA_TASK_ROOT}/git-askpass.sh

ENTRYPOINT ["/var/lang/bin/python"]
CMD ["/var/task/main.py"]
