ARG DEBIAN_IMAGE=debian:trixie
FROM ${DEBIAN_IMAGE}
ARG DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian
ENV DEBIAN_FRONTEND=noninteractive MOCHA_DEBIAN_MIRROR=${DEBIAN_MIRROR}
RUN rm -f /etc/apt/sources.list.d/debian.sources && \
    printf 'deb %s trixie main\ndeb %s trixie-backports main\n' "$DEBIAN_MIRROR" "$DEBIAN_MIRROR" > /etc/apt/sources.list && \
    dpkg --add-architecture armhf && apt-get update && \
    apt-get -y --no-install-recommends install \
      ca-certificates git curl python3 python3-mako python3-yaml python3-packaging \
      build-essential clang libclang-dev meson ninja-build pkg-config cmake patch bison flex bc \
      g++-arm-linux-gnueabihf binutils-arm-linux-gnueabihf device-tree-compiler u-boot-tools \
      debootstrap proot qemu-user cpio gzip xz-utils rsync kmod e2fsprogs fdisk \
      openssl libarchive-tools wayland-protocols libwayland-bin \
      libsdbus-c++-dev:armhf libwayland-dev:armhf libwayland-egl-backend-dev:armhf \
      libfreetype-dev:armhf libfontconfig-dev:armhf libcairo2-dev:armhf libpango1.0-dev:armhf \
      libharfbuzz-dev:armhf librsvg2-dev:armhf libxkbcommon-dev:armhf libglib2.0-dev:armhf \
      libsecret-1-dev:armhf libsodium-dev:armhf libpolkit-agent-1-dev:armhf libpolkit-gobject-1-dev:armhf \
      libpipewire-0.3-dev:armhf libwireplumber-0.5-dev:armhf libcurl4-gnutls-dev:armhf \
      libqalculate-dev:armhf libxml2-dev:armhf libmd4c-dev:armhf nlohmann-json3-dev \
      libtomlplusplus-dev:armhf libical-dev:armhf libegl-dev:armhf libgles-dev:armhf \
      libglvnd-dev:armhf libepoxy-dev:armhf libwebp-dev:armhf libjxl-dev:armhf libsndfile1-dev:armhf \
      libudev-dev:armhf libgbm-dev:armhf libinput-dev:armhf libseat-dev:armhf \
      libdisplay-info-dev:armhf libliftoff-dev:armhf libsystemd-dev:armhf libdbus-1-dev:armhf \
      libdrm-dev:armhf libexpat1-dev:armhf libelf-dev:armhf libzstd-dev:armhf zlib1g-dev:armhf \
      libgnutls28-dev:armhf liblua5.2-dev:armhf && \
    apt-get -y --no-install-recommends -t trixie-backports install rustc cargo libstd-rust-dev:armhf && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
COPY . /opt/mocha-flasher
WORKDIR /opt/mocha-flasher
ENTRYPOINT ["python3", "tools/bootstrap-source-build.py"]
