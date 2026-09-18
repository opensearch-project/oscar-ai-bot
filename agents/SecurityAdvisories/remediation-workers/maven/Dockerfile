# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# maven/Gradle ecosystem CVE remediation worker (container image, runs as an ECS
# Fargate task). Build context = the parent remediation-workers/ directory
# (so this can COPY the shared/ flow alongside the maven/ strategy).
FROM public.ecr.aws/lambda/python:3.12

# Unified maven worker (plugin + core). The plugin fix is a pure text edit of
# build.gradle, but the core fix bumps the version catalog and then runs
# ``./gradlew updateShas`` to regenerate the per-module .jar.sha1 checksums — so
# the image needs the full ``-devel`` JDK (not ``-headless``): updateShas compiles
# helper subprojects, so Gradle's toolchain needs javac. Gradle itself is not
# installed — each repo's ``gradlew`` wrapper downloads it at run time.
#
# gh CLI comes from GitHub's rpm repo (GPG-verified): the base image's microdnf
# lacks the config-manager plugin, so we write the repo file directly.
# findutils (xargs) is required by the gradlew wrapper script, which hard-fails
# with "xargs is not available" before it even downloads Gradle; the minimal
# Lambda base image doesn't ship it.
RUN dnf install -y git java-21-amazon-corretto-devel findutils && \
    printf '[gh-cli]\nname=packages for the GitHub CLI\nbaseurl=https://cli.github.com/packages/rpm\nenabled=1\ngpgcheck=1\ngpgkey=https://cli.github.com/packages/githubcli-archive-keyring.asc\n' > /etc/yum.repos.d/gh-cli.repo && \
    rpm --import https://cli.github.com/packages/githubcli-archive-keyring.asc && \
    dnf install -y gh && \
    dnf clean all && \
    git --version && gh --version && java -version

# gradlew finds the JDK via JAVA_HOME; the corretto rpm installs it here.
ENV JAVA_HOME=/usr/lib/jvm/java-21-amazon-corretto
# Gradle writes its distribution + caches under GRADLE_USER_HOME; the Lambda base
# image has no writable HOME, so point it at /tmp (writable on Fargate).
ENV GRADLE_USER_HOME=/tmp/.gradle

# main.py is the entrypoint: it reads the remediation payload from env vars and
# calls remediation.handle. We override the Lambda base image's runtime-client
# ENTRYPOINT to run it directly (the base image is used only for its AL2023 +
# Python, not the Lambda runtime).
COPY shared/remediation.py shared/git-askpass.sh maven/maven.py maven/llm_planner.py maven/main.py ${LAMBDA_TASK_ROOT}/
# git-askpass.sh feeds the token to git as the HTTPS password (via GIT_ASKPASS)
# so it never lands in a URL/argv/.git/config; ensure it's executable.
RUN chmod +x ${LAMBDA_TASK_ROOT}/git-askpass.sh

ENTRYPOINT ["/var/lang/bin/python"]
CMD ["/var/task/main.py"]
