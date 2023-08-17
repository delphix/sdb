#!/bin/bash -eux

# uname -a
# uname -r
# cat /etc/apt/sources.list
# sudo apt-get clean
# sudo apt-get update
# echo "deb http://ddebs.ubuntu.com $(lsb_release -cs) main restricted universe multiverse" | sudo tee -a /etc/apt/sources.list.d/ddebs.list
# echo "deb http://ddebs.ubuntu.com $(lsb_release -cs)-updates main restricted universe multiverse" | sudo tee -a /etc/apt/sources.list.d/ddebs.list
# echo "deb http://ddebs.ubuntu.com $(lsb_release -cs)-proposed main restricted universe multiverse" | sudo tee -a /etc/apt/sources.list.d/ddebs.list
# sudo apt install ubuntu-dbgsym-keyring
# sudo apt-get clean
# sudo apt-get update
# sudo apt-get install -y linux-image-$(uname -r)-dbgsym

kvers=$(uname -r)
ddeb_file=$(curl http://ddebs.ubuntu.com/pool/main/l/linux-azure/ |
	grep -Eo ">linux-image-(unsigned-)?$kvers(.*)amd64\.ddeb" |
	cut -c2-)

wget http://ddebs.ubuntu.com/pool/main/l/linux-azure/$ddeb_file
sudo dpkg -i $ddeb_file
rm $ddeb_file
