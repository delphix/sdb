#!/bin/bash -eux

if [[ ! -f /usr/local/bin/shfmt ]]; then
	sudo wget -nv -O /usr/local/bin/shfmt \
		https://github.com/mvdan/sh/releases/download/v3.0.2/shfmt_v3.0.2_linux_amd64
	sudo chmod +x /usr/local/bin/shfmt
fi
echo "shfmt version $(/usr/local/bin/shfmt -version) is installed."
