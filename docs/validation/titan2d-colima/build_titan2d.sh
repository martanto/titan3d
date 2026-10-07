#!/usr/bin/env bash
# Build Titan2D 4.2.0 from source on Ubuntu 24.04 (as used for this comparison).
# Usage: bash build_titan2d.sh [WORKDIR]   → binary at WORKDIR/inst/bin/titan
set -euo pipefail
W=${1:-$HOME/titan2d_wsp}
mkdir -p "$W/bld"

sudo apt-get install -y libhdf5-dev swig libtool libgdal-dev python3-dev python3-h5py autoconf automake g++ make

git clone --depth 1 https://github.com/TITAN2D/titan2d.git "$W/src"
cd "$W/src" && aclocal && autoheader && autoconf && automake --add-missing --copy

cd "$W/bld"
"$W/src/configure" --prefix="$W/inst" --enable-openmp --disable-java-gui --with-swig --with-gdal=/usr \
  PYTHON=/usr/bin/python3.12 PYTHON_CONFIG=/usr/bin/python3.12-config CXXFLAGS="-O2 -mtune=generic" \
  CPPFLAGS="-I/usr/include/hdf5/serial -I/usr/include/gdal" LDFLAGS="-L/usr/lib/x86_64-linux-gnu/hdf5/serial"

# -fopenmp at link time: tests/ticore/ticore_test otherwise fails to link (omp_get_thread_num).
make -j"$(nproc)" LDFLAGS="-L/usr/lib/x86_64-linux-gnu/hdf5/serial -fopenmp"
make install
echo "Titan2D: $W/inst/bin/titan"
