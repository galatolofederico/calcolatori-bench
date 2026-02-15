FROM mcr.microsoft.com/devcontainers/base:noble

ARG LIBCE_VERSION="4.3"
ARG QEMU_VERSION="9.2.2-3"

ENV HOME=/home/vscode/
ENV AUTOCORR=1

# Install build dependencies and tools
RUN apt update && apt install -y build-essential python3 python3-venv zlib1g-dev \
		libgtk-3-dev libpulse-dev libpixman-1-dev libjson-xs-perl \
		ninja-build ncurses-dev git \
		poppler-utils \
		curl unzip

RUN apt update && apt install -y gcc-multilib g++-multilib gdb

# Build libce and qemu-ce
RUN mkdir /dist
RUN chown vscode:vscode -R /dist

USER vscode
WORKDIR /dist

RUN wget https://calcolatori.iet.unipi.it/resources/libce-${LIBCE_VERSION}.tar.gz
RUN wget https://calcolatori.iet.unipi.it/resources/qemu-ce-${QEMU_VERSION}.tar.gz

RUN tar -xzvf libce-${LIBCE_VERSION}.tar.gz
RUN tar -xzvf qemu-ce-${QEMU_VERSION}.tar.gz

WORKDIR /dist/libce-${LIBCE_VERSION}
RUN make CE_QEMU_AUDIO=none && make install
RUN echo 'PATH=$HOME/CE/bin:$PATH' >> $HOME/.bashrc

WORKDIR /dist/qemu-ce-${QEMU_VERSION}
RUN sh /dist/qemu-ce-${QEMU_VERSION}/install

# Set up working directory
USER root
RUN mkdir -p /work && chown vscode:vscode /work
USER vscode
WORKDIR /work

# Install bun
USER vscode
RUN curl -fsSL https://bun.com/install | bash -s "bun-v1.3.9"

# Install patched opencode
RUN git clone --branch save-metadata https://github.com/galatolofederico/opencode.git /tmp/opencode
WORKDIR /tmp/opencode
RUN /home/vscode/.bun/bin/bun install
WORKDIR /tmp/opencode/packages/opencode
RUN /home/vscode/.bun/bin/bun run script/build.ts --single
RUN cp /tmp/opencode/packages/opencode/dist/opencode-linux-x64/bin/opencode /home/vscode/.bun/bin/opencode

ENV PATH="/home/vscode/CE/bin:/home/vscode/.bun/bin:${PATH}"

RUN opencode --version