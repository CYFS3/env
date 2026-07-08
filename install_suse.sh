#!/usr/bin/env bash

sudo zypper update -y

sudo zypper install python3 python3-pip gcc git ncurses-devel cross-arm-none-gcc11-bootstrap cross-arm-binutils qemu qemu-arm qemu-extra -y
python3 -m pip install scons requests tqdm kconfiglib
python3 -m pip install -U pyocd

url=https://raw.githubusercontent.com/CYFS3/env/feat_env/touch_env.sh

wget $url -O touch_env.sh
chmod 777 touch_env.sh
./touch_env.sh $@
rm touch_env.sh
